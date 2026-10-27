"""Meterless Scout Intent — PayProof implementation of the Scout specification
(github.com/Meterless/Meterless, engines/scout-intent: docs/risk-and-policy.md,
docs/execution-contract.md). The spec publishes no code; this follows its contracts.

Pipeline per request: Sense (intent from a declared registry) -> Interpret (bind parameters)
-> Guard (injection, policy/RBAC, PII) -> Route (capability set) -> Recommend (an HMAC-signed
execution contract, 5-minute TTL). The action service refuses to act on anything without a
valid contract whose capabilities cover the operation ("downstream engines act on contracts").

Two places untrusted text enters PayProof, with different policies:
  * user-submitted intake text (titles, narratives): an injection attempt BLOCKS the request
  * retrieved source records (memos, account names, reasons): the record is QUARANTINED — its
    text never reaches the model, the case gets a security finding, and any proposed action is
    escalated to controller approval. Numbers are still computed by deterministic code.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time

INTENTS = {  # intent registry: required permission and the exact capability set granted
    "dispute.file": {"permission": "case.file", "capabilities": ["intake.create", "world.ingest"], "risk": "low"},
    "action.propose": {"permission": "action.propose", "capabilities": ["case.investigate", "action.create"], "risk": "low"},
    "action.approve": {"permission": "action.approve", "capabilities": ["action.decide"], "risk": "medium"},
    "action.execute": {"permission": "action.execute", "capabilities": ["payroll.sim.write", "ticket.sim.write"], "risk": "high"},
}
TTL_S = 300

# Injection check (pattern + role drift + out-of-band tool references), per risk-and-policy.md §1.
INJECTION_PATTERNS = [
    ("pattern", re.compile(r"\b(ignore|disregard|forget|override)\b[^.]{0,40}\b(previous|prior|above|earlier|all|any|system)\b[^.]{0,20}\b(instructions?|prompts?|rules?|policy|policies|guardrails?)", re.I)),
    ("pattern", re.compile(r"(</?\s*system\s*>|\[/?INST\]|<\|im_(start|end)\|>|^\s*(system|assistant)\s*:)", re.I | re.M)),
    ("pattern", re.compile(r"\b(new|updated|real)\s+(system\s+)?(instructions?|prompt)\s*:", re.I)),
    ("role-drift", re.compile(r"\byou\s+(are|act\s+as|must\s+act\s+as|will\s+be)\s+(now\s+)?(an?\s+|the\s+)?(admin|administrator|controller|approver|root|system|developer|payroll\s+ops)\b", re.I)),
    ("role-drift", re.compile(r"\b(pretend|roleplay|role-play)\b[^.]{0,30}\b(you|to\s+be)\b", re.I)),
    ("tool-ref", re.compile(r"(/api/[a-z/_-]+|\b(execute|approve|mark)\s+(the\s+|this\s+)?(payroll\s+)?(adjustment|action|payout)s?\s+(immediately|now|without)|\bauto-?approve\b|\bset\s+(status|verdict|proof_status)\s+to\b)", re.I)),
    ("tool-ref", re.compile(r"\b(drop\s+table|delete\s+from|insert\s+into|update\s+\w+\s+set|union\s+select)\b", re.I)),
]
PII_PATTERNS = {
    "email": re.compile(r"[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,24}", re.I),
    "phone": re.compile(r"\+?\d[\d\s().-]{8,}\d"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "credential": re.compile(r"\b(nvapi-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._-]{16,})\b"),
}


def injection_check(text: str) -> dict:
    evidence, kinds = [], []
    for kind, pat in INJECTION_PATTERNS:
        m = pat.search(text or "")
        if m:
            kinds.append(kind)
            evidence.append(f"{kind}@{m.start()}")  # metadata only: the payload is never logged
    score = min(1.0, 0.6 * len(kinds)) if kinds else 0.0
    return {"detected": bool(kinds), "kind": kinds[0] if kinds else None, "kinds": sorted(set(kinds)), "score": round(score, 2),
            "evidence": evidence}


def redact(text: str) -> tuple[str, list[dict]]:
    redactions = []
    for cls, pat in PII_PATTERNS.items():
        def sub(m, cls=cls):
            redactions.append({"class": cls, "at": m.start()})
            return f"[{cls.upper()}]"
        text = pat.sub(sub, text)
    return text, redactions


def scan_records(case: dict) -> list[dict]:
    """Guard every free-text field of every retrieved source record (and the dispute narrative)."""
    hits = []
    targets = [("dispute", case["dispute"])] + [(sysname, r) for sysname, blk in case["sources"].items() for r in blk["records"]]
    for system, rec in targets:
        for field, value in rec.items():
            if isinstance(value, str) and len(value) > 12 and field not in ("id", "type", "effective_at", "recorded_at"):
                res = injection_check(value)
                if res["detected"]:
                    hits.append({"record_id": rec["id"], "system": system, "field": field, **res})
    return hits


class ScoutError(Exception):
    def __init__(self, code, message, status=403, risk=None):
        super().__init__(message)
        self.code, self.message, self.status, self.risk = code, message, status, risk


class Scout:
    def __init__(self, secret: bytes | None = None, clock=time.time):
        env = os.environ.get("PAYPROOF_CONTRACT_SECRET")
        self.secret = secret or (env.encode() if env else secrets.token_bytes(32))
        self.clock = clock
        self.issued = 0

    def _sign(self, body: dict) -> str:
        canon = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        return hmac.new(self.secret, canon.encode(), hashlib.sha256).hexdigest()

    def decide(self, intent: str, user: dict, params: dict | None = None, texts: dict | None = None,
               escalate: bool = False, parent_id: str | None = None) -> dict:
        # 1. Sense
        spec = INTENTS.get(intent)
        if not spec:
            raise ScoutError("UNKNOWN_INTENT", f"intent {intent!r} is not in the registry", 400)
        # 3. Guard: policy gate (RBAC)
        if spec["permission"] not in user["perms"]:
            raise ScoutError("POLICY_BLOCK", f"role {user['role']} lacks {spec['permission']} for {intent}", 403,
                             {"level": "block", "flags": [{"layer": "policy", "result": "block"}]})
        flags, redactions = [], []
        # Guard: injection check on user-supplied text
        for field, text in (texts or {}).items():
            res = injection_check(text)
            if res["detected"]:
                raise ScoutError("INJECTION_BLOCKED", f"field {field!r} contains an embedded instruction ({', '.join(res['kinds'])}); "
                                 "request refused", 422, {"level": "block", "flags": [{"layer": "injection", "field": field, **res}]})
            _, red = redact(text)
            redactions += [{"field": field, **r} for r in red]
        level = spec["risk"]
        if escalate:
            flags.append({"layer": "scope", "result": "warn", "reason": "quarantined source text in evidence"})
            level = {"low": "medium", "medium": "high", "high": "high"}[level]
        now = self.clock()
        self.issued += 1
        body = {
            "contractId": f"SC-{int(now * 1000):x}-{self.issued:04d}", "parentId": parent_id,
            "intent": {"primary": intent, "parameters": params or {}, "confidence": 1.0},
            "risk": {"level": level, "flags": flags, "redactions": redactions,
                     "approvals": ["controller"] if escalate else []},
            "toolPlan": [{"tool": c} for c in spec["capabilities"]],
            "scope": {"user": user["id"], "role": user["role"], "capabilities": list(spec["capabilities"])},
            "issuedAt": now, "expiresAt": now + TTL_S, "signedBy": "scout",
        }
        return {**body, "signature": self._sign(body)}

    def verify(self, contract: dict | None, capability: str, intent: str | None = None, user_id: str | None = None):
        if not contract:
            raise ScoutError("NO_CONTRACT", "downstream engines refuse to act without an execution contract")
        body = {k: v for k, v in contract.items() if k != "signature"}
        if not hmac.compare_digest(self._sign(body), contract.get("signature", "")):
            raise ScoutError("BAD_SIGNATURE", "execution contract signature invalid")
        if self.clock() > contract["expiresAt"]:
            raise ScoutError("CONTRACT_EXPIRED", "execution contract expired; request a fresh decision", 409)
        if capability not in contract["scope"]["capabilities"]:
            raise ScoutError("OUT_OF_SCOPE", f"capability {capability} not granted by contract")
        if intent and contract["intent"]["primary"] != intent:
            raise ScoutError("WRONG_INTENT", "contract was issued for a different intent")
        if user_id and contract["scope"]["user"] != user_id:
            raise ScoutError("WRONG_SUBJECT", "contract was issued to a different user")
        return True
