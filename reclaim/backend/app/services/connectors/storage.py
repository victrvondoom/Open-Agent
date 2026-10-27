from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.connectors.models import (
    ActionResult,
    ExecutionMode,
    OperationState,
)

OPERATIONS_FILE = Path("datasets") / "app_store" / "connector_operations.jsonl"


def _dump_model(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def save_operation(result: ActionResult) -> None:
    OPERATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OPERATIONS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_dump_model(result), ensure_ascii=True, default=str) + "\n")


def load_operations(connector_id: str | None = None) -> dict[str, ActionResult]:
    if not OPERATIONS_FILE.exists():
        return {}
    ops: dict[str, ActionResult] = {}
    with OPERATIONS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if connector_id and data.get("connector_id") != connector_id:
                    continue
                if "state" in data and isinstance(data["state"], str):
                    data["state"] = OperationState(data["state"])
                if "execution_mode" in data and isinstance(data["execution_mode"], str):
                    data["execution_mode"] = ExecutionMode(data["execution_mode"])
                op = ActionResult(**data)
                ops[op.operation_id] = op
            except Exception:
                continue
    return ops


def list_operations_for_case(case_id: str) -> list[ActionResult]:
    all_ops = load_operations()
    return [op for op in all_ops.values() if op.case_id == case_id]
