from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.services.connectors.models import (
    ActionResult,
    ConnectorManifest,
    ConnectorStatus,
    PreparedAction,
)


class BaseConnector(ABC):
    """Abstract Base Class for all RECLAIM Action Fabric Connectors."""

    @abstractmethod
    def describe_capabilities(self) -> ConnectorManifest:
        """Return the connector specification, capabilities, and schemas."""
        raise NotImplementedError

    def requires_approval(self, action_id: str) -> bool:
        """Server-side approval policy, read from this connector's own manifest:
        every write or approval-gated capability -- and any action the manifest
        doesn't declare -- needs a human approval token, whatever flag a
        PreparedAction carries."""
        for capability in self.describe_capabilities().capabilities:
            if capability.action_id == action_id:
                return capability.requires_human_approval or capability.is_write
        return True

    @abstractmethod
    def validate_input(self, action_id: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate input payload against the action's schema and constraints."""
        raise NotImplementedError

    @abstractmethod
    def prepare_action(
        self,
        action_id: str,
        payload: dict[str, Any],
        case_id: str,
        execution_mode: str = "sandbox",
    ) -> PreparedAction:
        """Formulate a prepared action with consequence analysis and human approval requirements."""
        raise NotImplementedError

    @abstractmethod
    def execute_action(
        self,
        prepared_action: PreparedAction,
        idempotency_key: str,
        approval_token: str | None = None,
    ) -> ActionResult:
        """Execute the prepared action. Requires approval_token if requires_human_approval is True."""
        raise NotImplementedError

    @abstractmethod
    def check_status(self, operation_id: str) -> ActionResult:
        """Check status of an asynchronous or ongoing operation."""
        raise NotImplementedError

    @abstractmethod
    def reconcile_result(self, operation_id: str) -> dict[str, Any]:
        """Reconcile outcome with provider/carrier records."""
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self) -> ConnectorStatus:
        """Check connector connectivity, latency, and sandbox readiness."""
        raise NotImplementedError
