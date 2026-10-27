from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, get_current_user
from app.database.postgres.repositories import case_repository
from app.services.connectors.approval_gate import approval_gate, parameters_digest
from app.services.connectors.models import (
    ActionResult,
    ConnectorManifest,
    ConnectorStatus,
    PreparedAction,
)
from app.services.connectors.registry import connector_registry

router = APIRouter()


class PrepareActionRequest(BaseModel):
    action_id: str
    case_id: str
    payload: dict[str, Any]
    execution_mode: str = "sandbox"


# approve/execute accept the prepared action echoed back from /prepare, or just
# its prepared_action_id. Either way only the server-side copy persisted at
# /prepare is approved or executed; an echoed copy must match it.
class HumanApprovalRequest(BaseModel):
    prepared_action: PreparedAction | None = None
    prepared_action_id: str | None = None
    user_id: str = ""
    consent_statement: str


class ExecuteActionRequest(BaseModel):
    prepared_action: PreparedAction | None = None
    prepared_action_id: str | None = None
    idempotency_key: str
    approval_token: str | None = None


def _echoed_copy_mismatch(echoed: PreparedAction, stored: PreparedAction) -> str | None:
    """Name of the first bound field where a client's echoed copy differs from the server-side record."""
    for field in ("connector_id", "action_id", "case_id", "execution_mode"):
        if getattr(echoed, field) != getattr(stored, field):
            return field
    if parameters_digest(echoed.parameters) != parameters_digest(stored.parameters):
        return "parameters"
    return None


async def _load_prepared_action(
    echoed: PreparedAction | None,
    prepared_action_id: str | None,
    user: CurrentUser,
) -> PreparedAction:
    """Resolve the caller's own server-side prepared action (404 otherwise).
    Its requires_human_approval flag and parameters come from the server,
    never from the request."""
    requested_id = prepared_action_id or (echoed.prepared_action_id if echoed else None)
    if not requested_id or (echoed is not None and echoed.prepared_action_id != requested_id):
        raise HTTPException(status_code=400, detail="Provide the prepared_action_id returned by /prepare")
    stored = connector_registry.get_prepared_action(requested_id, user.id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Prepared action not found or access denied")
    case = await case_repository.get_case(stored.case_id, user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or access denied")
    if echoed is not None:
        mismatch = _echoed_copy_mismatch(echoed, stored)
        if mismatch:
            raise HTTPException(
                status_code=403,
                detail=f"Prepared action {mismatch} does not match the server-side record; prepare the action again",
            )
    return stored


async def _load_owned_operation(connector_id: str, operation_id: str, user: CurrentUser) -> ActionResult:
    """An operation is visible only to the owner of the case it ran against (404 otherwise)."""
    try:
        operation = connector_registry.check_status(connector_id, operation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Operation record not found")
    if not await case_repository.get_case(operation.case_id, user.id):
        raise HTTPException(status_code=404, detail="Operation record not found")
    return operation


@router.get("", response_model=list[ConnectorManifest])
async def list_connectors() -> list[ConnectorManifest]:
    """Discover all registered RECLAIM Action Fabric connectors and capabilities."""
    return connector_registry.list_manifests()


@router.get("/health", response_model=list[ConnectorStatus])
async def check_all_connectors_health() -> list[ConnectorStatus]:
    """Probe connectivity, latency, and sandbox readiness across all connectors."""
    return connector_registry.healthcheck_all()


@router.get("/{connector_id}", response_model=ConnectorManifest)
async def get_connector_manifest(connector_id: str) -> ConnectorManifest:
    """Introspect specific connector capabilities and parameters."""
    try:
        conn = connector_registry.get(connector_id)
        return conn.describe_capabilities()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found")


@router.post("/{connector_id}/prepare", response_model=PreparedAction)
async def prepare_connector_action(
    connector_id: str,
    req: PrepareActionRequest,
    user: CurrentUser = Depends(get_current_user),
) -> PreparedAction:
    """Formulate an action, determine if human approval is required, and estimate consequences."""
    case = await case_repository.get_case(req.case_id, user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or access denied")
    try:
        return connector_registry.prepare(
            connector_id=connector_id,
            action_id=req.action_id,
            payload=req.payload,
            case_id=req.case_id,
            execution_mode=req.execution_mode,
            owner_id=user.id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/approve")
async def approve_action_manually(
    req: HumanApprovalRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Human approval gate: grant explicit user consent and generate an unforgeable approval token."""
    prepared = await _load_prepared_action(req.prepared_action, req.prepared_action_id, user)
    # Bind approval identity strictly to authenticated user
    approver_id = user.id
    token = approval_gate.issue_approval(
        prepared_action=prepared,
        user_id=approver_id,
        consent_statement=req.consent_statement,
    )
    return {
        "status": "APPROVED",
        "approval_token": token,
        "prepared_action_id": prepared.prepared_action_id,
        "approved_by": approver_id,
    }


@router.post("/{connector_id}/execute", response_model=ActionResult)
async def execute_connector_action(
    connector_id: str,
    req: ExecuteActionRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ActionResult:
    """Execute prepared action. Blocks if required human approval token is missing or invalid."""
    prepared = await _load_prepared_action(req.prepared_action, req.prepared_action_id, user)
    try:
        return connector_registry.execute(
            connector_id=connector_id,
            prepared_action=prepared,
            idempotency_key=req.idempotency_key,
            approval_token=req.approval_token,
            approver_id=user.id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connector execution error: {str(e)}")


@router.get("/{connector_id}/operations/{operation_id}", response_model=ActionResult)
async def get_operation_status(
    connector_id: str,
    operation_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ActionResult:
    """Check live status of an asynchronous connector operation."""
    return await _load_owned_operation(connector_id, operation_id, user)


@router.get("/{connector_id}/operations/{operation_id}/reconcile")
async def reconcile_operation(
    connector_id: str,
    operation_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Reconcile action result against carrier/provider status."""
    await _load_owned_operation(connector_id, operation_id, user)
    try:
        return connector_registry.reconcile(connector_id, operation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Operation record not found")


@router.get("/cases/{case_id}/operations", response_model=list[ActionResult])
async def list_case_operations(
    case_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> list[ActionResult]:
    """Retrieve all executed connector operations for a specific case."""
    case = await case_repository.get_case(case_id, user.id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or access denied")
    return connector_registry.list_case_operations(case_id)

