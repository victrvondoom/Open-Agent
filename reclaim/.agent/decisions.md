# Architectural Decisions — RECLAIM Action Fabric & Core Engine

## Decision 1: Switch-Independent Action Fabric
- **Context**: The mission requires adopting useful design principles (shared case context, declarative connector capabilities, lifecycle tracking, human authorization) without taking any proprietary code or dependencies from Switch.
- **Decision**: Implement a native Python & TypeScript `ReclaimActionFabric` in `app/services/connectors/`.
- **Connector Interface**:
  - `describe_capabilities() -> ConnectorManifest`
  - `validate_input(action: str, payload: dict) -> ValidationResult`
  - `prepare_action(action: str, payload: dict, case_context: dict) -> PreparedAction`
  - `execute_action(prepared_action_id: str, approval_token: str) -> ActionResult`
  - `check_status(operation_id: str) -> StatusResult`
  - `reconcile_result(operation_id: str) -> ReconciliationResult`
  - `healthcheck() -> HealthResult`

## Decision 2: Flight Cancellation & Refund Vertical Slice
- **Context**: Need a real end-to-end demonstrable connector for consumer claims.
- **Decision**: Deliver `AviationRefundConnector` implementing the DGCA CAR Section 3 Series M Part IV & EU 261 cancellation dispute rules. It provides deterministic sandbox/mock execution with full schema validation, approval token gating, idempotency keys, and reconciliation.

## Decision 3: Recursive Regulation-Aware Text Splitter
- **Context**: Naive character splitters fail when single separators are missing or break statutory numbering like "Section 3.2".
- **Decision**: Implement `RecursiveRegulationTextSplitter` in `app/rag/regulation_splitter.py`.
- **Separators**: `["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]` with statutory token protection regexes.
- **Default Constraints**: 200 max characters, 20 character overlap, Unicode safe (English, Tamil, Hindi, multilingual).

## Decision 4: Transparent Mathematical Optimization Model
- **Context**: Decision ranking must avoid arbitrary hand-waving or fake metrics.
- **Decision**: Implement `ReclaimDecisionEngine` in `app/services/decision_engine.py` computing normalized utility:
  $$U(a) = w_1 \cdot \hat{B}(a) - w_2 \cdot \hat{C}(a) - w_3 \cdot \hat{D}(a) - w_4 \cdot \hat{R}(a) - w_5 \cdot \hat{P}(a)$$
  with constraint validation (deadlines, missing evidence, action reversibility).
