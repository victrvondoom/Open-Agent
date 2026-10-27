---
doc: spec
status: approved
---

# RECLAIM — Technical Specification

## How This Works, In Plain Language
RECLAIM is organized as an evidence-grounded action pipeline:
1. **Intake & Segmentation**: A user enters their grievance. The **Recursive Regulation Text Splitter** breaks down governing statutes (DGCA CAR Series M Part IV & EU 261/2004) into fine-grained passages without cutting through statutory identifiers like "Section 3.2".
2. **Decision Engine**: Rather than giving vague legal advice, the **Reclaim Decision Engine** evaluates multiple action paths using a normalized utility function $U(a) = w_1 B(a) - w_2 C(a) - w_3 D(a) - w_4 R(a) - w_5 P(a)$ and validates missing evidence and statutory limitation deadlines.
3. **Action Fabric**: The chosen path is prepared through the **Aviation Refund Connector**, producing a transparent consequence summary and recovery calculation.
4. **Human Approval Gate**: Consequential actions require an explicit user approval token before any external carrier dispatch occurs.
5. **Execution & Audit**: In verified sandbox mode, the action dispatches deterministically, returns an official carrier claim reference, logs state transitions, and supports status polling and reconciliation.

## The Core Journey Through the System
1. User submits flight dispute payload (`pnr="PNR7788"`, `airline="IndiGo"`, `cancellation_notice_hours=12`, `ticket_amount=7500`).
2. Client queries `POST /api/v1/split` with legal text → receives verified chunks respecting the 200-character budget and citations.
3. Client queries `POST /api/v1/connectors/reclaim.connectors.aviation_refund/prepare` → connector generates `PreparedAction` with `requires_human_approval=True`.
4. Client queries `POST /api/v1/decision/optimize` → optimizer ranks Direct Claim ($U=0.28$) over AirSewa Escalation and DCDRC Forum Filing.
5. User reviews summary and signs consent → client calls `POST /api/v1/connectors/approve` → receives cryptographic `approval_token`.
6. Client invokes `POST /api/v1/connectors/reclaim.connectors.aviation_refund/execute` with token & idempotency key → receives `ActionResult(status="completed", carrier_claim_id="CLM-AIR-...")`.

## Stack
- **Backend**: Python 3.12, FastAPI 0.115, Pydantic v2, Pytest.
- **Agent Orchestrator**: LangGraph 1.0, Claude Opus 5.5 / Gemini / OpenAI multi-provider router.
- **RAG & Storage**: Custom recursive regulation splitter, Qdrant vector store (JSONL fallback), Neo4j knowledge graph (JSONL fallback).
- **Frontend**: Next.js 15.5, React 19, TypeScript, Tailwind CSS, Lucide icons, Framer Motion.

## Where It Runs and How Someone Tries It
- **Backend**:
  ```bash
  cd backend
  python -m pytest tests/test_action_fabric_and_decision.py tests/test_regulation_splitter.py
  python -m uvicorn app.main:app --port 8000 --reload
  ```
- **Frontend**:
  ```bash
  cd frontend
  npm run dev
  ```
- Open browser at `http://localhost:3000`.

## Look and Feel
- Cream and bone canvas (`#fcfaf5`), high-contrast typography, warm amber accents (`#f59e0b`), solid 2px borders (`#231f1d`), crisp shadows (`2px 2px 0px #231f1d`).
- Fonts: Figtree (sans-serif), EB Garamond (legal serif), JetBrains Mono (statutory code/telemetry).

## Components & File Structure
```
backend/
├── app/
│   ├── api/routes/
│   │   ├── connectors.py         # Connector registry and execution endpoints
│   │   ├── decision.py           # Mathematical utility optimizer route
│   │   └── split.py              # Recursive text splitting endpoint
│   ├── rag/
│   │   └── regulation_splitter.py # Recursive regulation splitter with statutory protection
│   └── services/
│       ├── connectors/
│       │   ├── approval_gate.py  # Explicit human approval gate & single-use tokens
│       │   ├── aviation_refund.py# Airline cancellation & refund vertical slice
│       │   ├── base.py           # BaseConnector abstract class
│       │   ├── models.py         # Pydantic schemas for Action Fabric
│       │   └── registry.py       # Global connector registry
│       └── decision_engine.py    # Multi-objective utility optimizer
├── tests/
│   ├── test_action_fabric_and_decision.py
│   └── test_regulation_splitter.py
frontend/
├── app/
│   ├── dashboard/
│   │   ├── connectors/page.tsx   # Action Fabric & Approval Center
│   │   ├── decision-optimizer/page.tsx # Decision Engine Path Optimizer
│   │   └── text-splitter/page.tsx# Developer & Legal Splitter Inspector
devpost/
├── scope.md
├── prd.md
└── spec.md
```

## Important Failure Modes & Mitigations
- **Unapproved Action Dispatch**: If a write action is dispatched without an approval token, the gate raises `PermissionError` (HTTP 403 Forbidden).
- **Token Replay Attack**: Once consumed, an approval token is invalidated immediately; duplicate calls are rejected.
- **Oversized Legal Texts**: If no newline or punctuation separator exists, the recursive splitter falls back to empty-string slicing, guaranteeing that the configured character budget is never exceeded.
