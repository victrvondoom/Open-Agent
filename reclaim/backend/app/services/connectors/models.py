from __future__ import annotations

import enum
from typing import Any
from pydantic import BaseModel, Field


class ExecutionMode(str, enum.Enum):
    SANDBOX = "sandbox"
    LIVE = "live"
    DETERMINISTIC_MOCK = "mock"


class ActionRiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ApprovalState(str, enum.Enum):
    NOT_REQUIRED = "not_required"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OperationState(str, enum.Enum):
    PREPARED = "prepared"
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    RECONCILED = "reconciled"


class ActionCapability(BaseModel):
    action_id: str
    name: str
    description: str
    is_write: bool = False
    requires_human_approval: bool = True
    is_reversible: bool = False
    risk_level: ActionRiskLevel = ActionRiskLevel.MEDIUM
    required_permissions: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class ConnectorManifest(BaseModel):
    connector_id: str
    name: str
    version: str
    domain: str
    description: str
    execution_modes: list[ExecutionMode] = Field(default_factory=lambda: [ExecutionMode.SANDBOX, ExecutionMode.LIVE])
    auth_type: str = "api_key"
    rate_limit: str = "60 req/min"
    timeout_seconds: int = 30
    retry_policy: str = "exponential_backoff_max_3"
    capabilities: list[ActionCapability]


class PreparedAction(BaseModel):
    prepared_action_id: str
    connector_id: str
    action_id: str
    case_id: str
    execution_mode: ExecutionMode = ExecutionMode.SANDBOX
    requires_human_approval: bool
    approval_state: ApprovalState
    approval_token: str | None = None
    parameters: dict[str, Any]
    summary_for_human: str
    consequences: list[str]
    reversibility: bool
    estimated_benefit: float = 0.0
    estimated_cost: float = 0.0
    created_at: str


class ActionResult(BaseModel):
    operation_id: str
    connector_id: str
    action_id: str
    case_id: str
    state: OperationState
    execution_mode: ExecutionMode
    provider_reference: str | None = None
    idempotency_key: str
    output_data: dict[str, Any] = Field(default_factory=dict)
    human_approved_by: str | None = None
    executed_at: str
    error_message: str | None = None


class ConnectorStatus(BaseModel):
    connector_id: str
    healthy: bool
    latency_ms: float
    active_mode: ExecutionMode
    last_health_check: str
    message: str = "Ready"
