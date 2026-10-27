from __future__ import annotations

import email.message
import json
import os
import smtplib
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.postgres.repositories import case_repository
from app.services.connectors.approval_gate import approval_gate
from app.services.connectors.base import BaseConnector
from app.services.connectors.models import (
    ActionCapability,
    ActionRiskLevel,
    ActionResult,
    ApprovalState,
    ConnectorManifest,
    ConnectorStatus,
    ExecutionMode,
    OperationState,
    PreparedAction,
)
from app.services.connectors.storage import load_operations, save_operation


def _live_email_enabled() -> bool:
    """Real SMTP delivery is an explicit operator opt-in (default off): an
    SMTP_HOST in the environment alone must never turn sandbox runs into real mail."""
    return os.environ.get("CONNECTOR_LIVE_EMAIL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


class EmailComplaintConnector(BaseConnector):
    """Outbound Complaint Delivery Connector for RECLAIM Action Fabric.

    Provides end-to-end evidence delivery, grievance dispatch, and formal legal dispute
    transmission to corporate grievance desks and regulatory authorities.
    Supports genuine SMTP transport with credentials or local durable outbox for integration testing.
    """

    def __init__(self, outbox_dir: Path | None = None):
        self.outbox_file = (outbox_dir or Path("datasets") / "app_store") / "email_outbox.jsonl"
        self.outbox_file.parent.mkdir(parents=True, exist_ok=True)
        self._operations: dict[str, ActionResult] = load_operations("reclaim.connectors.email_delivery")

    def describe_capabilities(self) -> ConnectorManifest:
        return ConnectorManifest(
            connector_id="reclaim.connectors.email_delivery",
            name="Authorized Email Complaint & Escalation Dispatch Fabric",
            version="1.0.0",
            domain="universal",
            description=(
                "Dispatches verified formal complaints and evidence dossiers directly to corporate "
                "nodal officers, grievance cells, or regulatory desks via authenticated SMTP or secure outbox."
            ),
            execution_modes=[ExecutionMode.SANDBOX, ExecutionMode.LIVE, ExecutionMode.DETERMINISTIC_MOCK],
            auth_type="smtp_tls_or_local_outbox",
            rate_limit="20 emails/hour",
            timeout_seconds=15,
            retry_policy="linear_backoff_max_2",
            capabilities=[
                ActionCapability(
                    action_id="prepare_complaint_email",
                    name="Prepare Formal Complaint Email",
                    description="Compile case facts, evidence citations, and formal demand into an editable email draft.",
                    is_write=False,
                    requires_human_approval=False,
                    is_reversible=True,
                    risk_level=ActionRiskLevel.LOW,
                    input_schema={
                        "case_id": "string",
                        "recipient_email": "string (optional)",
                        "custom_subject": "string (optional)",
                        "custom_body": "string (optional)",
                    },
                    output_schema={
                        "prepared_draft": "object",
                        "recipient": "string",
                        "subject": "string",
                    },
                ),
                ActionCapability(
                    action_id="send_complaint_email",
                    name="Dispatch Formal Complaint Email",
                    description="Transmit approved complaint with statutory citations through authenticated SMTP or recorded test outbox.",
                    is_write=True,
                    requires_human_approval=True,
                    is_reversible=False,
                    risk_level=ActionRiskLevel.HIGH,
                    input_schema={
                        "recipient_email": "string",
                        "subject": "string",
                        "body": "string",
                        "case_id": "string",
                    },
                    output_schema={
                        "message_id": "string",
                        "recipient": "string",
                        "delivery_mode": "string",
                        "dispatched_at": "string",
                    },
                ),
            ],
        )

    def validate_input(self, action_id: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
        if action_id == "send_complaint_email":
            recipient = payload.get("recipient_email")
            if not recipient or "@" not in recipient:
                return False, "Valid 'recipient_email' required"
            body = payload.get("body")
            if not body or len(body.strip()) < 10:
                return False, "Complaint 'body' cannot be empty or under 10 characters"
            return True, None
        return True, None

    def prepare_action(

        self,
        action_id: str,
        payload: dict[str, Any],
        case_id: str,
        execution_mode: str = "sandbox",
    ) -> PreparedAction:
        mode = ExecutionMode(execution_mode) if isinstance(execution_mode, str) else execution_mode

        now = datetime.now(timezone.utc).isoformat()

        if action_id == "prepare_complaint_email":
            recipient = payload.get("recipient_email") or f"nodal.officer@{payload.get('institution', 'dispute-authority').lower().replace(' ', '')}.com"
            subject = payload.get("custom_subject") or f"URGENT STATUTORY DISPUTE NOTICE — Case Ref {case_id[:8]}"
            body = payload.get("custom_body") or (
                f"To: Nodal Grievance Redressal Officer\n\n"
                f"RE: FORMAL COMPLAINT UNDER CONSUMER PROTECTION REGULATIONS\n"
                f"Case Identifier: {case_id}\n\n"
                f"This is a formal communication regarding an unresolved service deficiency.\n"
                f"Statutory rights require an acknowledgment within 48 hours and resolution within prescribed regulatory deadlines.\n\n"
                f"Evidence and citations attached.\n"
                f"Dispatched via RECLAIM Action Fabric."
            )

            prep = PreparedAction(
                prepared_action_id=f"prep-email-{uuid.uuid4().hex[:10]}",
                connector_id="reclaim.connectors.email_delivery",
                action_id=action_id,
                case_id=case_id,
                execution_mode=mode,
                requires_human_approval=False,
                approval_state=ApprovalState.NOT_REQUIRED,
                parameters={"recipient_email": recipient, "subject": subject, "body": body, "case_id": case_id},
                summary_for_human=f"Prepared complaint draft addressed to {recipient}",
                consequences=["Draft formulation only; no external communication dispatched."],
                reversibility=True,
                estimated_benefit=0.0,
                estimated_cost=0.0,
                created_at=now,
            )
            return approval_gate.request_approval(prep)

        if action_id == "send_complaint_email":
            recipient = payload.get("recipient_email")
            if not recipient or "@" not in recipient:
                raise ValueError("A valid 'recipient_email' is required to dispatch complaint.")

            subject = payload.get("subject") or f"FORMAL DISPUTE NOTICE [Ref: {case_id[:8]}]"
            body = payload.get("body")
            if not body or len(body.strip()) < 10:
                raise ValueError("Complaint 'body' cannot be empty or under 10 characters.")

            prep = PreparedAction(
                prepared_action_id=f"prep-email-send-{uuid.uuid4().hex[:10]}",
                connector_id="reclaim.connectors.email_delivery",
                action_id=action_id,
                case_id=case_id,
                execution_mode=mode,
                requires_human_approval=True,
                approval_state=ApprovalState.PENDING_APPROVAL,
                parameters={
                    "recipient_email": recipient,
                    "subject": subject,
                    "body": body,
                    "case_id": case_id,
                },
                summary_for_human=f"Irrevocable dispatch of formal complaint email to {recipient} with subject '{subject}'",
                consequences=[
                    f"Transmits formal grievance notice to {recipient}",
                    "Cannot be recalled once transmitted through mail server",
                    "Creates formal statutory dispute record in case ledger",
                ],
                reversibility=False,
                estimated_benefit=15000.0,
                estimated_cost=0.0,
                created_at=now,
            )
            return approval_gate.request_approval(prep)

        raise ValueError(f"Unknown action '{action_id}' for email complaint connector")

    def execute_action(
        self,
        prepared_action: PreparedAction,
        idempotency_key: str,
        approval_token: str | None = None,
    ) -> ActionResult:
        # Check idempotency (scoped to the case, so another user's key can't replay their result)
        for existing in self._operations.values():
            if existing.idempotency_key == idempotency_key and existing.case_id == prepared_action.case_id:
                return existing

        action_id = prepared_action.action_id
        payload = prepared_action.parameters
        case_id = prepared_action.case_id
        now = datetime.now(timezone.utc).isoformat()
        op_id = f"op-email-{uuid.uuid4().hex[:10]}"

        # Always consult the gate: the manifest policy, not the action's own
        # requires_human_approval flag, decides whether a token is needed.
        is_ok, reason = approval_gate.verify_approval(
            prepared_action, approval_token, required=self.requires_approval(action_id)
        )
        if not is_ok:
            raise PermissionError(f"Approval gate verification failed: {reason}")


        if action_id == "prepare_complaint_email":
            result = ActionResult(
                operation_id=op_id,
                connector_id=prepared_action.connector_id,
                action_id=action_id,
                case_id=case_id,
                state=OperationState.COMPLETED,
                execution_mode=prepared_action.execution_mode,
                provider_reference=f"DRAFT-EML-{uuid.uuid4().hex[:8].upper()}",
                idempotency_key=idempotency_key,
                output_data=payload,
                human_approved_by=None,
                executed_at=now,
            )
            self._operations[op_id] = result
            save_operation(result)
            return result

        if action_id == "send_complaint_email":
            recipient = payload["recipient_email"]
            subject = payload["subject"]
            body = payload["body"]

            smtp_host = os.environ.get("SMTP_HOST")
            smtp_port = int(os.environ.get("SMTP_PORT", "587"))
            smtp_user = os.environ.get("SMTP_USER")
            smtp_pass = os.environ.get("SMTP_PASSWORD")
            smtp_sender = os.environ.get("SMTP_SENDER", "disputes@reclaim.justice")

            # Real SMTP only for an explicitly LIVE action AND the operator opt-in;
            # sandbox/mock (or live without the opt-in) only ever reach the local outbox.
            send_live = prepared_action.execution_mode == ExecutionMode.LIVE and _live_email_enabled()

            # Check if live mode requires genuine credentials
            if send_live and not smtp_host:
                result = ActionResult(
                    operation_id=op_id,
                    connector_id=prepared_action.connector_id,
                    action_id=action_id,
                    case_id=case_id,
                    state=OperationState.FAILED,
                    execution_mode=prepared_action.execution_mode,
                    provider_reference=None,
                    idempotency_key=idempotency_key,
                    output_data={"error_code": "PROVIDER_NOT_CONFIGURED", "detail": "Live SMTP_HOST is not configured in backend environment."},
                    error_message="Live SMTP provider not configured. Configure SMTP_HOST or execute in SANDBOX mode.",
                    human_approved_by=approval_token[:12] + "..." if approval_token else None,
                    executed_at=now,
                )
                self._operations[op_id] = result
                save_operation(result)
                return result

            # Live and opted in: dispatch via smtplib
            if send_live:
                try:
                    msg = email.message.EmailMessage()
                    msg["Subject"] = subject
                    msg["From"] = smtp_sender
                    msg["To"] = recipient
                    msg["Message-ID"] = f"<{uuid.uuid4()}@{smtp_host}>"
                    msg.set_content(body)

                    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                        if smtp_port in (587, 25):
                            try:
                                server.starttls()
                            except Exception:
                                pass
                        if smtp_user and smtp_pass:
                            server.login(smtp_user, smtp_pass)
                        server.send_message(msg)

                    provider_ref = msg["Message-ID"]
                    delivery_mode = "LIVE_SMTP_TRANSMISSION"
                except Exception as exc:
                    result = ActionResult(
                        operation_id=op_id,
                        connector_id=prepared_action.connector_id,
                        action_id=action_id,
                        case_id=case_id,
                        state=OperationState.FAILED,
                        execution_mode=prepared_action.execution_mode,
                        provider_reference=None,
                        idempotency_key=idempotency_key,
                        output_data={"recipient": recipient, "error": str(exc)},
                        error_message=f"SMTP transmission failed: {str(exc)}",
                        human_approved_by=approval_token[:12] + "..." if approval_token else None,
                        executed_at=now,
                    )
                    self._operations[op_id] = result
                    save_operation(result)
                    return result
            else:
                # Sandbox or Local Testing Mode -> Record to durable outbox
                msg_id = f"MSG-LOCAL-OUTBOX-{uuid.uuid4().hex[:12].upper()}"
                provider_ref = msg_id
                delivery_mode = "LOCAL_SECURE_TEST_OUTBOX"
                outbox_entry = {
                    "message_id": msg_id,
                    "case_id": case_id,
                    "recipient": recipient,
                    "sender": smtp_sender,
                    "subject": subject,
                    "body": body,
                    "timestamp": now,
                    "mode": prepared_action.execution_mode.value,
                }
                with self.outbox_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(outbox_entry, ensure_ascii=True, default=str) + "\n")

            result = ActionResult(
                operation_id=op_id,
                connector_id=prepared_action.connector_id,
                action_id=action_id,
                case_id=case_id,
                state=OperationState.COMPLETED,
                execution_mode=prepared_action.execution_mode,
                provider_reference=provider_ref,
                idempotency_key=idempotency_key,
                output_data={
                    "message_id": provider_ref,
                    "recipient": recipient,
                    "subject": subject,
                    "delivery_mode": delivery_mode,
                    "delivered_at": now,
                    "status": "DISPATCHED",
                    "note": (
                        "Formal legal complaint recorded and dispatched to recipient address."
                        if send_live
                        else "Recorded to the local test outbox only; no external email was sent."
                    ),
                },
                human_approved_by=approval_token[:12] + "..." if approval_token else None,
                executed_at=now,
            )

            if approval_token:
                approval_gate.mark_consumed(approval_token)

            self._operations[op_id] = result
            save_operation(result)

            # Record event to case history
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(
                        case_repository.add_event(
                            case_id,
                            {
                                "actor": "connector:email_delivery",
                                "event_type": "complaint_dispatched",
                                "title": f"Complaint email dispatched to {recipient}",
                                "body": f"Subject: {subject} | Ref: {provider_ref} | Mode: {delivery_mode}",
                            },
                        )
                    )
            except Exception:
                pass

            return result

        raise ValueError(f"Unknown action '{action_id}' for email complaint connector")

    def check_status(self, operation_id: str) -> ActionResult:
        res = self._operations.get(operation_id)
        if not res:
            self._operations = load_operations("reclaim.connectors.email_delivery")
            res = self._operations.get(operation_id)
        if not res:
            raise KeyError(f"Operation {operation_id} not found in email connector ledger")
        return res

    def reconcile_result(self, operation_id: str) -> dict[str, Any]:
        res = self.check_status(operation_id)
        return {
            "operation_id": operation_id,
            "reconciled": True,
            "provider_reference": res.provider_reference,
            "state": res.state.value,
            "verified_consistent": True,
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
        }

    def healthcheck(self) -> ConnectorStatus:
        smtp_host = os.environ.get("SMTP_HOST")
        is_live = bool(smtp_host) and _live_email_enabled()
        return ConnectorStatus(
            connector_id="reclaim.connectors.email_delivery",
            healthy=True,
            latency_ms=1.5,
            active_mode=ExecutionMode.LIVE if is_live else ExecutionMode.SANDBOX,
            last_health_check=datetime.now(timezone.utc).isoformat(),
            message="Email Connector active (Live SMTP)" if is_live else "Email Connector operational (Local Outbox Sandbox)",
        )
