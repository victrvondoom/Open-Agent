"""Approval-gated actions with postcondition verification.

State machine (enforced here, not in the UI):

    PROPOSED -> VALIDATED -> AWAITING_APPROVAL -> APPROVED -> EXECUTED -> VERIFIED
    any non-terminal -> REJECTED | EXPIRED ; APPROVED/EXECUTED -> FAILED ; FAILED -> EXECUTED (retry, same key)

Authorization is decided from the authenticated user's role, never from model output.
All side effects go to a *simulated* adapter; no real payroll system is touched.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .money import D
from .sources import sha
from . import world_model as wm
from .llm import ModelClient
from .workflow import investigate, source_fingerprint

ROOT = Path(__file__).resolve().parent.parent

USERS_PATH = ROOT / "data" / "users.json"


def load_users(path: Path = USERS_PATH) -> dict:
    """token -> user. Demo-only authentication: synthetic users selected via X-Demo-User."""
    raw = json.loads(path.read_text())["users"]
    return {t: {**u, "perms": set(u["perms"])} for t, u in raw.items()}


USERS = load_users()
ROLE_LIMIT_KEY = {"finance_approver": "finance_approver", "controller": "controller"}
ROLE_RANK = {"finance_approver": 1, "controller": 2}

TRANSITIONS = {
    "PROPOSED": {"VALIDATED", "REJECTED", "EXPIRED"},
    "VALIDATED": {"AWAITING_APPROVAL", "REJECTED", "EXPIRED"},
    "AWAITING_APPROVAL": {"APPROVED", "REJECTED", "EXPIRED"},
    "APPROVED": {"EXECUTED", "FAILED", "EXPIRED"},
    "EXECUTED": {"VERIFIED", "FAILED"},
    "FAILED": {"EXECUTED"},
    "VERIFIED": set(), "REJECTED": set(), "EXPIRED": set(),
}
TERMINAL = {"VERIFIED", "REJECTED", "EXPIRED"}
APPROVAL_TTL = timedelta(hours=24)


class ActionError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class AuditLog:
    """Append-only, hash-chained log. Contains ids and amounts only (no names/emails)."""

    def __init__(self, path: Path | None):
        self.entries, self.path = [], path
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

    def append(self, event, actor, **details):
        prev = self.entries[-1]["hash"] if self.entries else "GENESIS"
        entry = {"seq": len(self.entries) + 1, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "event": event, "actor": actor, "details": details, "prev_hash": prev}
        entry["hash"] = sha({k: v for k, v in entry.items() if k != "hash"})
        self.entries.append(entry)
        if self.path:
            with self.path.open("a") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry

    def verify_chain(self):
        prev = "GENESIS"
        for e in self.entries:
            if e["prev_hash"] != prev or e["hash"] != sha({k: v for k, v in e.items() if k != "hash"}):
                return False
            prev = e["hash"]
        return True


class SimulatedAdapter:
    """Simulated payroll + case-management system. Idempotent on idempotency_key."""

    def __init__(self):
        self.ledger, self.tickets, self.writes, self.fail_next = [], [], 0, False

    def apply(self, action):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated adapter outage (injected)")
        for row in self.ledger + self.tickets:
            if row["idempotency_key"] == action["idempotency_key"]:
                return row, False
        self.writes += 1
        if action["type"] == "PREPARE_PAYROLL_ADJUSTMENT":
            row = {"id": f"SIM-ADJ-{len(self.ledger) + 1:04d}", "type": "payroll_line", "batch_id": "PB-SIM-ADJ",
                   "employee_id": action["employee_id"], "opportunity_id": action["opportunity_id"],
                   "line_type": "adjustment", "amount": action["amount"], "reference_id": action["id"],
                   "idempotency_key": action["idempotency_key"], "simulated": True}
            self.ledger.append(row)
        else:
            row = {"id": f"SIM-TKT-{len(self.tickets) + 1:04d}", "kind": action["type"], "case_id": action["case_id"],
                   "amount": action.get("amount"), "idempotency_key": action["idempotency_key"], "simulated": True}
            self.tickets.append(row)
        return row, True

    def ledger_for(self, employee_id, opportunity_id):
        return [r for r in self.ledger if r["employee_id"] == employee_id and r["opportunity_id"] == opportunity_id]


class ActionService:
    def __init__(self, source, plans, audit_path: Path | None = ROOT / "var" / "audit.jsonl", clock=None):
        self.source, self.plans = source, plans
        self.audit = AuditLog(audit_path)
        self.adapter = SimulatedAdapter()
        self.actions: dict[str, dict] = {}
        self.worlds: dict[str, wm.WorldModel] = {}  # action id -> Meterless World Model snapshot at proposal
        self.lock = threading.RLock()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ helpers
    def user(self, token):
        u = USERS.get(token or "")
        if not u:
            raise ActionError("UNAUTHENTICATED", "unknown or missing user", 401)
        return u

    def investigate(self, case_id, use_model: bool = True):
        case = self.source.load_case(case_id)
        d = case["dispute"]
        return investigate(case, self.plans, ledger=self.adapter.ledger_for(d["employee_id"], d["opportunity_id"]),
                           model=ModelClient(enabled=None if use_model else False))

    def _move(self, a, to, actor, **details):
        if to not in TRANSITIONS[a["state"]]:
            raise ActionError("INVALID_TRANSITION", f"{a['state']} -> {to} not allowed", 409)
        a["history"].append({"from": a["state"], "to": to, "actor": actor, "at": self.clock().isoformat(timespec="seconds"), **details})
        a["state"] = to
        e = self.audit.append(f"ACTION_{to}", actor, action_id=a["id"], case_id=a["case_id"], type=a["type"],
                              amount=a.get("amount"), **details)
        a["audit_seqs"].append(e["seq"])

    def _stale(self, a):
        """Two independent staleness signals; either one expires the action (fail closed).
        1. Meterless World Model: re-ingest current sources into the world captured at proposal;
           the engine's idempotency contract says an unchanged batch reports changed=False.
        2. sha256 fingerprint of the source snapshot."""
        case = self.source.load_case(a["case_id"])
        report = wm.ingest_case(self.worlds[a["id"]], case)
        fp_changed = source_fingerprint(case) != a["preconditions"]["source_fingerprint"]
        a["staleness_checks"].append({"world_model_changed": report["changed"], "world_model_new_or_changed": report["processed"],
                                      "fingerprint_changed": fp_changed, "agree": report["changed"] == fp_changed,
                                      "at": self.clock().isoformat(timespec="seconds")})
        if report["changed"] or fp_changed:
            return (f"Meterless World Model ingest reported changed={report['changed']} "
                    f"({report['processed']} new/changed source records); fingerprint changed={fp_changed}")
        return None

    def get(self, action_id):
        a = self.actions.get(action_id)
        if not a:
            raise ActionError("NOT_FOUND", "no such action", 404)
        return a

    # ------------------------------------------------------------------ operations
    def propose(self, case_id, token):
        u = self.user(token)
        if "action.propose" not in u["perms"]:
            self.audit.append("DENIED", u["id"], op="propose", case_id=case_id)
            raise ActionError("FORBIDDEN", f"role {u['role']} cannot propose actions", 403)
        with self.lock:
            inv = self.investigate(case_id, use_model=False)
            pa = inv["proposed_action"]
            for a in self.actions.values():
                if a["idempotency_key"] == pa["idempotency_key"] and a["state"] not in {"REJECTED", "EXPIRED"}:
                    return a  # idempotent proposal
            aid = "ACT-" + sha([pa["idempotency_key"], len(self.actions)])[:10]
            a = {**pa, "id": aid, "state": "PROPOSED", "proposed_by": u["id"], "history": [], "audit_seqs": [],
                 "proof_hash": inv["proof_hash"], "staleness_checks": [], "approved_by": None, "approved_at": None, "receipt": None,
                 "created_at": self.clock().isoformat(timespec="seconds")}
            self.actions[aid] = a
            world = wm.WorldModel(namespace=f"{case_id}/{aid}")
            snap = wm.ingest_case(world, self.source.load_case(case_id))
            self.worlds[aid] = world
            a["preconditions"]["world_model_state_hash"] = snap["state_hash"]
            a["audit_seqs"].append(self.audit.append("ACTION_PROPOSED", u["id"], action_id=aid, case_id=case_id,
                                                     type=a["type"], amount=a.get("amount"), run_id=inv["run_id"])["seq"])
            # System validation: proof must be sound and the validator must have passed
            if not inv["validation"]["passed"] or pa.get("blocked_by_validator"):
                self._move(a, "REJECTED", "SYSTEM", reason="validator failed")
                return a
            self._move(a, "VALIDATED", "SYSTEM", proof_status=inv["proof_status"])
            self._move(a, "AWAITING_APPROVAL", "SYSTEM", required_permission=a["required_permission"])
            return a

    def decide(self, action_id, token, approve: bool, note: str = ""):
        u = self.user(token)
        with self.lock:
            a = self.get(action_id)
            reasons = []
            if "action.approve" not in u["perms"]:
                reasons.append(f"role {u['role']} lacks action.approve")
            elif ROLE_RANK.get(u["role"], 0) < ROLE_RANK[a["required_permission"]]:
                reasons.append(f"requires {a['required_permission']}; {u['role']} limit "
                               f"{self.plans['approval_limits'][ROLE_LIMIT_KEY[u['role']]]}")
            elif a["amount"] and D(a["amount"]) > D(self.plans["approval_limits"][ROLE_LIMIT_KEY[u["role"]]]):
                reasons.append("amount exceeds approval limit")
            if u["id"] == a["proposed_by"]:
                reasons.append("segregation of duties: proposer cannot approve")
            if u["id"] == a["employee_id"]:
                reasons.append("conflict of interest: subject employee cannot approve")
            if reasons:
                self.audit.append("DENIED", u["id"], op="approve", action_id=action_id, reasons=reasons)
                raise ActionError("FORBIDDEN", "; ".join(reasons), 403)
            if a["state"] != "AWAITING_APPROVAL":
                raise ActionError("INVALID_STATE", f"action is {a['state']}", 409)
            if stale := self._stale(a):
                self._move(a, "EXPIRED", "SYSTEM", reason=f"STALE_EVIDENCE before approval: {stale}")
                raise ActionError("STALE_EVIDENCE", "source records changed since the proposal; action expired", 409)
            if approve:
                a["approved_by"], a["approved_at"] = u["id"], self.clock().isoformat(timespec="seconds")
                self._move(a, "APPROVED", u["id"], note=note[:200])
            else:
                self._move(a, "REJECTED", u["id"], note=note[:200])
            return a

    def execute(self, action_id, token, idempotency_key):
        u = self.user(token)
        with self.lock:
            a = self.get(action_id)
            if "action.execute" not in u["perms"]:
                self.audit.append("DENIED", u["id"], op="execute", action_id=action_id)
                raise ActionError("FORBIDDEN", f"role {u['role']} cannot execute actions", 403)
            if idempotency_key != a["idempotency_key"]:
                raise ActionError("IDEMPOTENCY_MISMATCH", "idempotency key does not match the approved action", 409)
            if a["state"] in ("EXECUTED", "VERIFIED"):
                self.audit.append("DUPLICATE_SUPPRESSED", u["id"], action_id=action_id)
                return a  # at-most-once: return the existing receipt
            if a["state"] not in ("APPROVED", "FAILED"):
                raise ActionError("NOT_APPROVED", f"action is {a['state']}; approval required before execution", 409)
            if u["id"] == a["approved_by"] and u["role"] != "controller":
                raise ActionError("FORBIDDEN", "approver cannot execute", 403)
            approved_at = datetime.fromisoformat(a["approved_at"])
            if self.clock() - approved_at > APPROVAL_TTL:
                self._move(a, "EXPIRED", "SYSTEM", reason="approval expired")
                raise ActionError("EXPIRED", "approval expired", 409)
            # Re-check preconditions against current sources
            if stale := self._stale(a):
                self._move(a, "EXPIRED", "SYSTEM", reason=f"STALE_EVIDENCE at execution: {stale}")
                raise ActionError("STALE_EVIDENCE", "source records changed after approval; action expired", 409)
            already_written = any(r["idempotency_key"] == a["idempotency_key"] for r in self.adapter.ledger + self.adapter.tickets)
            current = self.investigate(a["case_id"], use_model=False)
            if not already_written and current["calculation"]["paid"] != a["preconditions"]["expected_paid_before"]:
                if a["state"] != "FAILED":
                    self._move(a, "FAILED", "SYSTEM", reason="precondition: paid total changed")
                raise ActionError("PRECONDITION_FAILED", "paid total changed since approval", 409)
            try:
                row, created = self.adapter.apply(a)
            except RuntimeError as exc:
                if a["state"] != "FAILED":
                    self._move(a, "FAILED", "SYSTEM", reason=str(exc))
                raise ActionError("EXECUTION_FAILED", str(exc), 502)
            self._move(a, "EXECUTED", u["id"], adapter_row=row["id"], created=created)
            post = self.verify_postcondition(a, row)
            if not post["passed"]:
                # A failed postcondition never yields a receipt; it is recorded as a failure instead.
                self._move(a, "FAILED", "SYSTEM", reason="postcondition failed", postcondition=False)
                a["receipt"] = None
                a["failure"] = {"adapter_record": row["id"], "postcondition": post, "audit_seq": self.audit.entries[-1]["seq"]}
                raise ActionError("POSTCONDITION_FAILED", "simulated state does not match the expected result; no receipt issued", 500)
            self._move(a, "VERIFIED", "SYSTEM", postcondition=True)
            last = self.audit.entries[-1]
            a["receipt"] = {
                "receipt_id": "RCPT-" + sha([a["id"], row["id"]])[:12], "action_id": a["id"], "type": a["type"],
                "amount": a.get("amount"), "idempotency_key": a["idempotency_key"], "adapter": "simulated",
                "adapter_record": row, "proposed_by": a["proposed_by"], "approved_by": a["approved_by"],
                "executed_by": u["id"], "executed_at": self.clock().isoformat(timespec="seconds"),
                "run_id": a["run_id"], "proof_hash": a["proof_hash"],
                "source_fingerprint": a["preconditions"]["source_fingerprint"], "postcondition": post,
                "audit_seq": last["seq"], "audit_hash": last["hash"], "audit_chain_valid": self.audit.verify_chain(),
            }
            return a

    def verify_postcondition(self, a, row):
        """Independent re-read of the simulated system state after execution."""
        if a["type"] == "PREPARE_PAYROLL_ADJUSTMENT":
            after = self.investigate(a["case_id"], use_model=False)
            calc = after["calculation"]
            ok = calc["paid"] == a["preconditions"]["expected_due"] and D(calc["delta"]) == 0
            return {"passed": ok, "check": "re-investigated payout: paid == expected due and variance == 0",
                    "expected_paid": a["preconditions"]["expected_due"], "observed_paid": calc["paid"],
                    "observed_delta": calc["delta"], "ledger_writes": self.adapter.writes}
        found = [t for t in self.adapter.tickets if t["idempotency_key"] == a["idempotency_key"]]
        return {"passed": len(found) == 1, "check": "exactly one ticket exists for idempotency key",
                "observed_tickets": len(found)}

    def reset(self):
        with self.lock:
            self.actions.clear()
            self.worlds.clear()
            self.adapter = SimulatedAdapter()
            self.source.reset()
            self.audit.append("DEMO_RESET", "SYSTEM")


def late_credit_note(case_id, n=1):
    """A credit note that arrives late but is dated before the cutoff (stale-evidence demo)."""
    return {"id": f"CN-LATE-{case_id[5:]}-{n}", "type": "credit_note", "invoice_id": None, "amount": "1000.00",
            "issued_date": "2026-06-25", "reason": "late-posted service credit", "effective_at": "2026-06-25",
            "recorded_at": "2026-07-20T09:00:00Z"}
