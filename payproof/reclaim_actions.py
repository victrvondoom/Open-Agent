"""Approval-gated consumer actions (sandbox only) with stale-evidence invalidation.

    PROPOSED -> VALIDATED -> AWAITING_APPROVAL -> APPROVED -> EXECUTED -> VERIFIED
    any non-terminal -> REJECTED | EXPIRED ; APPROVED/EXECUTED -> FAILED ; FAILED -> EXECUTED (retry, same key)

Same contract as the payroll action service (actions.py): authorization comes from the authenticated
user's role and tenant, never from model output; segregation of duties; approval TTL; idempotency;
Scout execution contracts; two independent staleness signals (Meterless World Model re-ingest and the
source fingerprint) expire an approval. The sandbox grievance desk is the only side effect.
State persists under var/consumer/ so a restart keeps actions, proposal snapshots and the audit chain.
"""

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import world_model as wm
from .actions import ROLE_RANK, TRANSITIONS, ActionError, AuditLog
from .llm import ModelClient
from .money import D
from .reclaim_evidence import consumer_fingerprint, ingest_consumer_case
from .reclaim_verifier import investigate_consumer
from .scout import ScoutError
from .sources import sha

ROOT = Path(__file__).resolve().parent.parent
APPROVAL_TTL = timedelta(hours=24)
NON_TERMINAL = {"PROPOSED", "VALIDATED", "AWAITING_APPROVAL", "APPROVED", "FAILED"}


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class PersistentAuditLog(AuditLog):
    """Append-only, hash-chained, and reloaded across restarts (the chain is re-verified on load)."""

    def __init__(self, path: Path | None):
        self.entries, self.path = [], path
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.entries.append(json.loads(line))
        self.loaded_chain_valid = self.verify_chain()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)


class GrievanceSandbox:
    """Simulated institution grievance desk. Idempotent on idempotency_key; persisted; never contacts anyone."""

    def __init__(self, path: Path | None):
        self.path, self.rows, self.fail_next = path, [], False
        if path and path.exists():
            self.rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def apply(self, action: dict, actor: str) -> tuple[dict, bool]:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated grievance-desk outage (injected)")
        for row in self.rows:
            if row["idempotency_key"] == action["idempotency_key"]:
                return row, False
        row = {"id": f"SBX-GRV-{len(self.rows) + 1:04d}", "kind": action["type"], "case_id": action["case_id"],
               "tenant_id": action.get("tenant_id"), "institution": action.get("institution"), "amount": action.get("amount"),
               "letter_hash": (action.get("payload") or {}).get("letter_hash"), "idempotency_key": action["idempotency_key"],
               "submitted_by": actor, "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sandbox": True}
        self.rows.append(row)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        return row, True


class ConsumerActionService:
    def __init__(self, source, rulebook: dict, scout, memory=None, bridge=None, var_dir: Path | None = ROOT / "var" / "consumer",
                 clock=None):
        self.source, self.rulebook, self.scout, self.memory, self.bridge = source, rulebook, scout, memory, bridge
        self.var_dir = var_dir
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.RLock()
        self.audit = PersistentAuditLog(var_dir / "audit.jsonl" if var_dir else None)
        self.sandbox = GrievanceSandbox(var_dir / "sandbox.jsonl" if var_dir else None)
        self.actions: dict[str, dict] = {}
        self.worlds: dict[str, wm.WorldModel] = {}
        self.reports: dict[str, dict] = {}        # case_id -> latest investigation (no _world)
        self.history: dict[str, list] = {}        # case_id -> superseded runs
        self.proposal_reports: dict[str, dict] = {}
        if var_dir and (var_dir / "actions.json").exists():
            self.actions = json.loads((var_dir / "actions.json").read_text(encoding="utf-8"))
            for aid in self.actions:
                snap = var_dir / "snapshots" / f"{aid}.json"
                if snap.exists():
                    world = wm.WorldModel(namespace=f"consumer/{self.actions[aid]['case_id']}/{aid}")
                    ingest_consumer_case(world, json.loads(snap.read_text(encoding="utf-8")))
                    self.worlds[aid] = world

    # ------------------------------------------------------------------ persistence / access
    def _persist(self):
        if self.var_dir:
            _atomic_write(self.var_dir / "actions.json", json.dumps(self.actions, indent=1, default=str))

    def _now(self):
        return self.clock().isoformat(timespec="seconds")

    @staticmethod
    def can_view(user: dict, case: dict) -> bool:
        if user.get("tenant") != case.get("tenant_id"):
            return False
        if "case.view" in user["perms"]:
            return True
        return "consumer.view_own" in user["perms"] and case["dispute"].get("claimant_id") == user.get("claimant_id")

    def load_visible(self, case_id: str, user: dict) -> dict:
        try:
            case = self.source.load_case(case_id)
        except (KeyError, FileNotFoundError):
            raise ActionError("NOT_FOUND", "no such consumer case", 404)
        if not self.can_view(user, case):
            self.audit.append("DENIED", user["id"], op="consumer.case.view", case_id=case_id, reason="tenant/ownership")
            raise ActionError("NOT_FOUND", "no such consumer case", 404)  # never confirm existence across tenants
        return case

    def visible_cases(self, user: dict) -> list[str]:
        out = []
        for cid in self.source.list_case_ids():
            try:
                claim = self.source.load_claim(cid)
            except (KeyError, FileNotFoundError, ValueError):
                continue
            if self.can_view(user, claim):
                out.append(cid)
        return out

    # ------------------------------------------------------------------ investigation
    def investigate(self, case_id: str, user: dict, use_model: bool = True, record: bool = True) -> dict:
        case = self.load_visible(case_id, user)
        inv = investigate_consumer(case, self.rulebook, source=self.source, model=ModelClient(enabled=None if use_model else False),
                                   memory=self.memory)
        world = inv.pop("_world")
        if record:
            with self.lock:
                prev = self.reports.get(case_id)
                if prev and prev["run_id"] != inv["run_id"]:
                    self.history.setdefault(case_id, []).append({"run_id": prev["run_id"], "proof_hash": prev["proof_hash"],
                                                                 "source_fingerprint": prev["source_fingerprint"],
                                                                 "superseded_at": self._now(), "superseded_by": inv["run_id"],
                                                                 "stale": prev["source_fingerprint"] != inv["source_fingerprint"],
                                                                 "action": prev["proposed_action"]["type"],
                                                                 "amount": prev["proposed_action"]["amount"]})
                self.reports[case_id] = inv
        inv["_world"] = world
        return inv

    def latest(self, case_id: str, user: dict) -> dict:
        self.load_visible(case_id, user)
        rep = self.reports.get(case_id)
        if rep is None:
            rep = self.investigate(case_id, user)
            rep.pop("_world", None)
        return rep

    # ------------------------------------------------------------------ gate helpers
    def _contract(self, intent, user, capability, params=None, escalate=False):
        try:
            c = self.scout.decide(intent, user, params=params, escalate=escalate)
            self.scout.verify(c, capability, intent=intent, user_id=user["id"])
        except ScoutError as e:
            self.audit.append("DENIED", user["id"], op=intent, reason=e.code)
            raise ActionError("FORBIDDEN" if e.code == "POLICY_BLOCK" else e.code, e.message, e.status)
        return {k: c[k] for k in ("contractId", "issuedAt", "expiresAt", "signature")} | {"risk": c["risk"]["level"],
                                                                                          "capabilities": c["scope"]["capabilities"]}

    def _move(self, a, to, actor, **details):
        if to not in TRANSITIONS[a["state"]]:
            raise ActionError("INVALID_TRANSITION", f"{a['state']} -> {to} not allowed", 409)
        a["history"].append({"from": a["state"], "to": to, "actor": actor, "at": self._now(), **details})
        a["state"] = to
        e = self.audit.append(f"CONSUMER_ACTION_{to}", actor, action_id=a["id"], case_id=a["case_id"], tenant=a.get("tenant_id"),
                              type=a["type"], amount=a.get("amount"), **details)
        a["audit_seqs"].append(e["seq"])
        self._persist()

    def _stale(self, a) -> str | None:
        """Two independent signals; either one makes the evidence stale (fail closed)."""
        case = self.source.load_case(a["case_id"])
        world = self.worlds.get(a["id"])
        wm_changed = processed = None
        if world is not None:
            report = ingest_consumer_case(world, case)
            wm_changed, processed = report["changed"], report["processed"]
        fp_changed = consumer_fingerprint(case) != a["preconditions"]["source_fingerprint"]
        a["staleness_checks"].append({"world_model_changed": wm_changed, "world_model_new_or_changed": processed,
                                      "fingerprint_changed": fp_changed, "at": self._now()})
        if wm_changed or fp_changed or world is None:
            return (f"Meterless World Model changed={wm_changed} ({processed} new/changed record(s)); fingerprint changed={fp_changed}"
                    + ("; no proposal snapshot" if world is None else ""))
        return None

    def get(self, action_id: str, user: dict | None = None) -> dict:
        a = self.actions.get(action_id)
        if not a or (user is not None and a.get("tenant_id") != user.get("tenant")):
            raise ActionError("NOT_FOUND", "no such action", 404)
        return a

    def for_case(self, case_id: str) -> list[dict]:
        return [a for a in self.actions.values() if a["case_id"] == case_id]

    # ------------------------------------------------------------------ operations
    def propose(self, case_id: str, user: dict) -> dict:
        if "action.propose" not in user["perms"]:
            raise ActionError("FORBIDDEN", f"role {user['role']} cannot propose actions", 403)
        contract = self._contract("action.propose", user, "action.create", {"case_id": case_id, "domain": "consumer"})
        with self.lock:
            inv = self.investigate(case_id, user, use_model=False)
            world_case = self.source.load_case(case_id)
            inv.pop("_world", None)
            pa = inv["proposed_action"]
            for a in self.actions.values():
                if a["idempotency_key"] == pa["idempotency_key"] and a["state"] not in {"REJECTED", "EXPIRED"}:
                    return a  # idempotent proposal
            aid = "CACT-" + sha([pa["idempotency_key"], len(self.actions)])[:10]
            a = {**pa, "id": aid, "state": "PROPOSED", "proposed_by": user["id"], "history": [], "audit_seqs": [],
                 "proof_hash": inv["proof_hash"], "staleness_checks": [], "contracts": [contract], "approved_by": None,
                 "approved_at": None, "receipt": None, "created_at": self._now(), "domain": "consumer"}
            self.actions[aid] = a
            self.proposal_reports[aid] = inv
            world = wm.WorldModel(namespace=f"consumer/{case_id}/{aid}")
            snap = ingest_consumer_case(world, world_case)
            self.worlds[aid] = world
            a["preconditions"]["world_model_state_hash"] = snap["state_hash"]
            if self.var_dir:
                _atomic_write(self.var_dir / "snapshots" / f"{aid}.json", json.dumps(world_case, default=str))
            a["audit_seqs"].append(self.audit.append("CONSUMER_ACTION_PROPOSED", user["id"], action_id=aid, case_id=case_id,
                                                     tenant=a.get("tenant_id"), type=a["type"], amount=a.get("amount"),
                                                     run_id=inv["run_id"], proof_hash=inv["proof_hash"])["seq"])
            if not inv["validation"]["passed"] or pa.get("blocked_by_validator"):
                self._move(a, "REJECTED", "SYSTEM", reason="validator failed")
                return a
            self._move(a, "VALIDATED", "SYSTEM", proof_status=inv["proof_status"])
            self._move(a, "AWAITING_APPROVAL", "SYSTEM", required_permission=a["required_permission"])
            return a

    def decide(self, action_id: str, user: dict, approve: bool, note: str = "") -> dict:
        with self.lock:
            a = self.get(action_id, user)
            reasons = []
            limits = self.rulebook["approval_limits"]
            if "action.approve" not in user["perms"]:
                reasons.append(f"role {user['role']} lacks action.approve")
            elif ROLE_RANK.get(user["role"], 0) < ROLE_RANK[a["required_permission"]]:
                reasons.append(f"requires {a['required_permission']}; {user['role']} limit INR {limits.get(user['role'])}")
            elif a.get("amount") and D(a["amount"]) > D(limits.get(user["role"], "0")):
                reasons.append("amount exceeds approval limit")
            if user["id"] == a["proposed_by"]:
                reasons.append("segregation of duties: proposer cannot approve")
            if reasons:
                self.audit.append("DENIED", user["id"], op="consumer.approve", action_id=action_id, reasons=reasons)
                raise ActionError("FORBIDDEN", "; ".join(reasons), 403)
            if a["state"] != "AWAITING_APPROVAL":
                raise ActionError("INVALID_STATE", f"action is {a['state']}", 409)
            if stale := self._stale(a):
                self._move(a, "EXPIRED", "SYSTEM", reason=f"STALE_EVIDENCE before approval: {stale}")
                raise ActionError("STALE_EVIDENCE", "source records changed since the proposal; action expired - re-verify and re-propose", 409)
            a["contracts"].append(self._contract("action.approve", user, "action.decide", {"action_id": action_id, "approve": approve},
                                                 escalate=bool(a.get("escalated"))))
            if approve:
                a["approved_by"], a["approved_at"] = user["id"], self._now()
                self._move(a, "APPROVED", user["id"], note=note[:200])
            else:
                self._move(a, "REJECTED", user["id"], note=note[:200])
            return a

    def escalate(self, action_id: str, user: dict, note: str = "") -> dict:
        with self.lock:
            a = self.get(action_id, user)
            if not ({"action.approve", "action.propose"} & user["perms"]):
                raise ActionError("FORBIDDEN", f"role {user['role']} cannot escalate actions", 403)
            if a["state"] != "AWAITING_APPROVAL":
                raise ActionError("INVALID_STATE", f"only actions awaiting approval can be escalated (is {a['state']})", 409)
            if a["required_permission"] != "controller":
                a["required_permission"], a["escalated"] = "controller", True
                a["history"].append({"from": a["state"], "to": a["state"], "actor": user["id"], "at": self._now(),
                                     "reason": f"escalated to controller: {note[:200]}"})
                a["audit_seqs"].append(self.audit.append("CONSUMER_ACTION_ESCALATED", user["id"], action_id=action_id)["seq"])
                self._persist()
            return a

    def execute(self, action_id: str, user: dict, idempotency_key: str) -> dict:
        with self.lock:
            a = self.get(action_id, user)
            if "action.execute" not in user["perms"]:
                self.audit.append("DENIED", user["id"], op="consumer.execute", action_id=action_id)
                raise ActionError("FORBIDDEN", f"role {user['role']} cannot execute actions", 403)
            if idempotency_key != a["idempotency_key"]:
                raise ActionError("IDEMPOTENCY_MISMATCH", "idempotency key does not match the approved action", 409)
            if a["state"] in ("EXECUTED", "VERIFIED"):
                self.audit.append("DUPLICATE_SUPPRESSED", user["id"], action_id=action_id)
                return a  # at-most-once: replays return the existing receipt
            if a["state"] not in ("APPROVED", "FAILED"):
                raise ActionError("NOT_APPROVED", f"action is {a['state']}; approval required before execution", 409)
            if user["id"] == a["approved_by"] and user["role"] != "controller":
                raise ActionError("FORBIDDEN", "approver cannot execute", 403)
            if self.clock() - datetime.fromisoformat(a["approved_at"]) > APPROVAL_TTL:
                self._move(a, "EXPIRED", "SYSTEM", reason="approval expired")
                raise ActionError("EXPIRED", "approval expired", 409)
            if stale := self._stale(a):
                self._move(a, "EXPIRED", "SYSTEM", reason=f"STALE_EVIDENCE at execution: {stale}")
                raise ActionError("STALE_EVIDENCE", "source records changed after approval; approval invalidated - re-verify", 409)
            a["contracts"].append(self._contract("consumer.execute", user, "grievance.sandbox.submit", {"action_id": action_id}))
            try:
                row, created = self.sandbox.apply(a, user["id"])
            except RuntimeError as exc:
                if a["state"] != "FAILED":
                    self._move(a, "FAILED", "SYSTEM", reason=str(exc))
                raise ActionError("EXECUTION_FAILED", str(exc), 502)
            self._move(a, "EXECUTED", user["id"], adapter_row=row["id"], created=created)
            found = [r for r in self.sandbox.rows if r["idempotency_key"] == a["idempotency_key"]]
            post = {"passed": len(found) == 1 and found[0]["amount"] == a.get("amount")
                    and found[0]["letter_hash"] == (a.get("payload") or {}).get("letter_hash"),
                    "check": "exactly one sandbox submission for the key, with the approved amount and letter hash",
                    "observed_submissions": len(found)}
            if not post["passed"]:
                self._move(a, "FAILED", "SYSTEM", reason="postcondition failed", postcondition=False)
                a["failure"] = {"adapter_record": row["id"], "postcondition": post}
                raise ActionError("POSTCONDITION_FAILED", "sandbox state does not match the approved action; no receipt issued", 500)
            self._move(a, "VERIFIED", "SYSTEM", postcondition=True)
            last = self.audit.entries[-1]
            a["receipt"] = {"receipt_id": "RCPT-C-" + sha([a["id"], row["id"]])[:12], "action_id": a["id"], "type": a["type"],
                            "amount": a.get("amount"), "currency": "INR", "idempotency_key": a["idempotency_key"], "adapter": "sandbox",
                            "adapter_record": row, "proposed_by": a["proposed_by"], "approved_by": a["approved_by"],
                            "executed_by": user["id"], "executed_at": self._now(), "run_id": a["run_id"], "proof_hash": a["proof_hash"],
                            "source_fingerprint": a["preconditions"]["source_fingerprint"], "postcondition": post,
                            "audit_seq": last["seq"], "audit_hash": last["hash"], "audit_chain_valid": self.audit.verify_chain()}
            inv = self.proposal_reports.get(a["id"])
            mem = self.memory.record_verified(inv, a, tenant=a.get("tenant_id"), consumer=True) if (self.memory and inv) else None
            a["receipt"]["precedent_memory_id"] = mem["id"] if mem else None
            if mem:
                self.audit.append("PRECEDENT_STORED", "SYSTEM", action_id=a["id"], case_id=a["case_id"], memory_id=mem["id"])
            a["receipt"]["reclaim_mirror"] = self._mirror(a)
            self._persist()
            return a

    def _mirror(self, a) -> dict:
        """Best effort: record the receipt in the linked RECLAIM case timeline. Never blocks the action."""
        link = self.source.load_claim(a["case_id"]).get("reclaim") or {}
        if not (self.bridge and link.get("case_id")):
            return {"mirrored": False, "reason": "case not linked to RECLAIM"}
        try:
            ev = self.bridge.add_event(a["tenant_id"], link["case_id"], "payproof_action_executed",
                                       f"Sandbox {a['type']} verified ({a['receipt']['receipt_id']})",
                                       f"amount {a.get('amount')}; proof {a['proof_hash'][:16]}; approved by {a['approved_by']}")
            return {"mirrored": True, "reclaim_event_id": ev["id"]}
        except Exception as exc:  # the receipt is authoritative; the mirror is a convenience
            return {"mirrored": False, "reason": type(exc).__name__}

    # ------------------------------------------------------------------ automatic invalidation (source change)
    def revalidate(self, case_id: str, user: dict) -> dict:
        """1 detect source change  2 mark the previous proof stale  3 invalidate related approvals
           4 re-run verification  5 new explanation  6 require new approval if the action changed."""
        with self.lock:
            prev = self.reports.get(case_id)
            case = self.load_visible(case_id, user)
            fp_now = consumer_fingerprint(case)
            changed = prev is None or prev["source_fingerprint"] != fp_now
            invalidated = []
            for a in self.for_case(case_id):
                if a["state"] in NON_TERMINAL and a["preconditions"]["source_fingerprint"] != fp_now:
                    self._move(a, "EXPIRED", "SYSTEM", reason="STALE_EVIDENCE: source changed; approval invalidated by revalidation")
                    invalidated.append(a["id"])
            new = self.investigate(case_id, user)
            new.pop("_world", None)
            before = {k: prev["proposed_action"][k] for k in ("type", "amount")} if prev else None
            after = {k: new["proposed_action"][k] for k in ("type", "amount")}
            out = {"source_changed": changed, "previous_run_id": prev["run_id"] if prev else None, "new_run_id": new["run_id"],
                   "previous_proof_stale": bool(prev) and changed, "invalidated_actions": invalidated,
                   "action_before": before, "action_after": after, "action_changed": before != after if before else None,
                   "requires_new_approval": bool(invalidated) or (before is not None and before != after),
                   "new_proof_status": new["proof_status"], "new_explanation": new["explanation"]["decision"]}
            self.audit.append("CONSUMER_REVALIDATED", user["id"], case_id=case_id, source_changed=changed,
                              invalidated=invalidated, new_run_id=new["run_id"])
            return out

    def reset(self):
        with self.lock:
            for d in (self.actions, self.worlds, self.reports, self.history, self.proposal_reports):
                d.clear()
            self.sandbox.rows.clear()
            if self.var_dir:
                snaps = list((self.var_dir / "snapshots").glob("*.json")) if (self.var_dir / "snapshots").exists() else []
                for p in [self.var_dir / "actions.json", self.var_dir / "sandbox.jsonl"] + snaps:
                    p.unlink(missing_ok=True)
            self.source.reset()
            self.audit.append("CONSUMER_DEMO_RESET", "SYSTEM")
