from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.connectors.models import ApprovalState, ExecutionMode, PreparedAction

SECRET_SALT = "reclaim_action_fabric_secure_gate_salt_2026"
TOKEN_EXPIRY_SECONDS = 86400  # 24 hours


def _canonical(value: Any) -> Any:
    """JSON-equivalent normal form: integral floats collapse to ints, so a
    payload that round-trips through a JS client (7500.0 -> 7500) still
    hashes the same."""
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def parameters_digest(parameters: dict[str, Any]) -> str:
    """Canonical SHA-256 (sorted keys, no whitespace) of a prepared action's
    parameters -- the content an approval token is bound to."""
    canonical = json.dumps(_canonical(parameters), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ActionApprovalGate:
    """Explicit human approval checkpoint for consequential real-world actions.

    Backed by durable JSONL persistence so approval records survive restarts.
    """

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or Path("datasets") / "app_store"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.tokens_file = self.storage_dir / "action_approvals.jsonl"
        self.audit_file = self.storage_dir / "action_audit_log.jsonl"
        self.prepared_file = self.storage_dir / "prepared_actions.jsonl"
        self._approved_tokens: dict[str, dict[str, Any]] = {}
        self._audit_log: list[dict[str, Any]] = []
        self._prepared_actions: dict[str, dict[str, Any]] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Hydrate tokens and audit log from disk on startup."""
        if self.tokens_file.exists():
            with self.tokens_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            record = json.loads(line)
                            token = record.get("token")
                            if token:
                                self._approved_tokens[token] = record
                        except json.JSONDecodeError:
                            continue

        if self.audit_file.exists():
            with self.audit_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._audit_log.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

        if self.prepared_file.exists():
            with self.prepared_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if record.get("prepared_action_id"):
                            self._prepared_actions[record["prepared_action_id"]] = record

    def record_prepared_action(self, prepared_action: PreparedAction, owner_id: str) -> None:
        """Persist the server-side copy of a freshly prepared action. Approval
        and execution only ever use this copy, never one echoed back by a
        client, whose requires_human_approval flag and parameters can't be trusted."""
        record = {
            "prepared_action_id": prepared_action.prepared_action_id,
            "owner_id": owner_id,
            "parameters_sha256": parameters_digest(prepared_action.parameters),
            "prepared_action": prepared_action.model_dump(mode="json"),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._prepared_actions[prepared_action.prepared_action_id] = record
        with self.prepared_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def get_prepared_action(self, prepared_action_id: str, owner_id: str) -> PreparedAction | None:
        """The server-side copy of a prepared action, only for the user who prepared it."""
        record = self._prepared_actions.get(prepared_action_id)
        if not record or record.get("owner_id") != owner_id:
            return None
        return PreparedAction.model_validate(record["prepared_action"])

    def _save_token(self, token: str, record: dict[str, Any]) -> None:
        """Durable append/update of approval token."""
        self._approved_tokens[token] = record
        # Rewrite tokens file to reflect updated 'used' state safely
        with self.tokens_file.open("w", encoding="utf-8") as f:
            for rec in self._approved_tokens.values():
                f.write(json.dumps(rec, default=str) + "\n")

    def _append_audit(self, event: dict[str, Any]) -> None:
        """Append event to audit log file."""
        self._audit_log.append(event)
        with self.audit_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def request_approval(self, prepared_action: PreparedAction) -> PreparedAction:
        """Mark action as awaiting explicit approval."""
        if not prepared_action.requires_human_approval:
            prepared_action.approval_state = ApprovalState.NOT_REQUIRED
            return prepared_action

        prepared_action.approval_state = ApprovalState.PENDING_APPROVAL
        return prepared_action

    def issue_approval(
        self,
        prepared_action: PreparedAction,
        user_id: str,
        consent_statement: str,
    ) -> str:
        """Record explicit user approval and generate an unforgeable verification token."""
        raw_key = (
            f"{prepared_action.prepared_action_id}:{prepared_action.case_id}:"
            f"{prepared_action.connector_id}:{prepared_action.action_id}:{user_id}:"
            f"{time.time()}:{secrets.token_hex(8)}"
        )
        token = hmac.new(SECRET_SALT.encode(), raw_key.encode(), hashlib.sha256).hexdigest()

        now = datetime.now(timezone.utc).isoformat()
        digest = parameters_digest(prepared_action.parameters)
        # The token is bound to the exact content approved: verify_approval
        # rejects execution if any of these fields differ.
        record = {
            "token": token,
            "prepared_action_id": prepared_action.prepared_action_id,
            "case_id": prepared_action.case_id,
            "connector_id": prepared_action.connector_id,
            "action_id": prepared_action.action_id,
            "execution_mode": ExecutionMode(prepared_action.execution_mode).value,
            "parameters_sha256": digest,
            "user_id": user_id,
            "consent_statement": consent_statement,
            "approved_at": now,
            "timestamp": time.time(),
            "used": False,
        }

        self._save_token(token, record)
        self._append_audit({
            "event": "HUMAN_APPROVAL_GRANTED",
            "token": token[:12] + "...",
            "prepared_action_id": prepared_action.prepared_action_id,
            "case_id": prepared_action.case_id,
            "action_id": prepared_action.action_id,
            "parameters_sha256": digest,
            "user_id": user_id,
            "timestamp": now,
        })

        prepared_action.approval_state = ApprovalState.APPROVED
        prepared_action.approval_token = token
        return token

    def verify_approval(
        self,
        prepared_action: PreparedAction,
        token: str | None,
        user_id: str | None = None,
        required: bool = False,
    ) -> tuple[bool, str | None]:
        """Validate token before execution is permitted.

        `required` carries the caller's server-side policy (the connector
        manifest) and can only add the requirement: a PreparedAction claiming
        requires_human_approval=False can't talk its way past the gate.
        `user_id`, when given, must be the user the token was issued to."""
        if not (required or prepared_action.requires_human_approval):
            return True, None

        if not token:
            return False, "Action requires explicit human approval token before execution"

        record = self._approved_tokens.get(token)
        if not record:
            return False, "Invalid or unrecognized approval token"

        if record.get("used"):
            return False, "Approval token has already been consumed (idempotency enforcement)"

        # Check expiry
        issued_at = record.get("timestamp", 0)
        if time.time() - issued_at > TOKEN_EXPIRY_SECONDS:
            return False, "Approval token has expired"

        # Cryptographic and context binding checks
        if record.get("prepared_action_id") != prepared_action.prepared_action_id:
            return False, "Approval token mismatch for this prepared action ID"

        if record.get("action_id") != prepared_action.action_id:
            return False, "Approval token mismatch for this action type"

        if record.get("connector_id") != prepared_action.connector_id:
            return False, "Approval token mismatch for this connector"

        if record.get("case_id") != prepared_action.case_id:
            return False, "Approval token mismatch for this case"

        if record.get("execution_mode") != ExecutionMode(prepared_action.execution_mode).value:
            return False, "Approval token mismatch for this execution mode"

        # Tokens issued before content binding carry no digest and are refused too.
        if record.get("parameters_sha256") != parameters_digest(prepared_action.parameters):
            return False, "Approval token does not cover these action parameters"

        if user_id is not None and record.get("user_id") != user_id:
            return False, "Approval token was issued to a different user"

        return True, None

    def mark_consumed(self, token: str) -> None:
        """Mark token as consumed to prevent replay attacks and persist to disk."""
        if token in self._approved_tokens:
            self._approved_tokens[token]["used"] = True
            self._save_token(token, self._approved_tokens[token])
            self._append_audit({
                "event": "APPROVAL_TOKEN_CONSUMED",
                "token": token[:12] + "...",
                "consumed_at": datetime.now(timezone.utc).isoformat(),
            })

    def get_audit_trail(self, case_id: str | None = None) -> list[dict[str, Any]]:
        if case_id:
            return [e for e in self._audit_log if e.get("case_id") == case_id]
        return list(self._audit_log)


approval_gate = ActionApprovalGate()
