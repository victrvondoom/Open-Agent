# RECLAIM — Dynamic Functionality & Persistence Audit

**Date:** 2026-10-26  
**Auditor:** Antigravity Engineering Harness  
**Target:** Local RECLAIM Codebase (`c:\Users\Administrator\Downloads\CONSUMER`)

---

## 1. System Inventory & Interactive Feature Matrix

| Feature / UI Surface | Frontend Component | User Interaction | Backend API Endpoint | Input Source | Output Source | Persistence Mechanism | External Dependencies | Failure Behavior | Verified Status |
|---|---|---|---|---|---|---|---|---|---|
| **Case Creation** | `frontend/app/dashboard/new/page.tsx` | Voice dictate or text enter claim, select domain | `POST /api/v1/cases` | User form / Voice Flow | `case_repository.create_case()` | File-backed JSONL (`cases.jsonl`) / Postgres | Voice Flow API (optional, local fallback) | Displays error toast, keeps form state | **Real & Persistent** |
| **Document Upload** | `frontend/components/documents/` | Upload PDF or image evidence | `POST /api/v1/upload` & `POST /api/v1/case/upload` | File input | `storage_service.save_case_document()` | Local vault directory + `case_documents.jsonl` | Tesseract OCR / PDF parser | Rejects >10MB or invalid MIME | **Real & Persistent** |
| **Agent Analysis** | `frontend/components/analyses/` | Click "Run Analysis" / "Start Review" | `POST /api/v1/case/analyze` | Saved case & documents | `case_analysis_workflow.run()` (LangGraph) | `agent_runs.jsonl`, `appeals.jsonl`, `case_events.jsonl` | Claude / OpenAI / Gemini LLM API (local fallback) | Sets status to ERROR, logs trace | **Real & Persistent** |
| **Action Fabric Discovery** | `frontend/app/dashboard/connectors/page.tsx` | Page load / filter connectors | `GET /api/v1/connectors` | Connector registry | `connector_registry.list_manifests()` | Code-registered connector manifests | None | Empty state card | **Real & Dynamic** |
| **Action Preparation** | `frontend/app/dashboard/connectors/page.tsx` | Click "Prepare Action" | `POST /api/v1/connectors/{id}/prepare` | Case ID & parameters | `connector.prepare_action()` | Previously in-memory; now migrating to durable store | None | Returns 400 with validation error | **Needs Durable Store** |
| **Human Approval Gate** | `frontend/app/dashboard/connectors/page.tsx` | Click "Authorize & Sign Token" | `POST /api/v1/connectors/approve` | Prepared Action & User Consent | `approval_gate.issue_approval()` | Previously in-memory; now migrating to durable store | HMAC Secret Salt | Returns 403 on invalid token | **Needs Durable Store** |
| **Action Execution** | `frontend/app/dashboard/connectors/page.tsx` | Click "Execute Claim" | `POST /api/v1/connectors/{id}/execute` | Prepared Action + Token + Idempotency | `connector.execute_action()` | Previously in-memory; now migrating to durable store | Carrier Sandbox or Mail Provider | Returns 403 if unapproved, 500 on timeout | **Needs Durable Store** |
| **Email Complaint Delivery** | Action Fabric / Appeals | Send verified appeal letter to carrier | `POST /api/v1/connectors/reclaim.connectors.email_delivery/execute` | Case appeal draft & recipient | `EmailDeliveryConnector` | Durable outbox + `case_events.jsonl` | SMTP or local test outbox | Rejects if unapproved or SMTP down | **To Implement** |
| **Regulation Text Splitting** | `frontend/app/dashboard/text-splitter/page.tsx` | Paste text or upload doc, set budget sliders | `POST /api/v1/split` | Text input, chunk size, overlap | `RecursiveRegulationTextSplitter.split_text()` | Transient API output | None | Validates overlap < chunk_size | **Real & Dynamic** |
| **Document Ingestion Splitting** | Backend RAG indexing pipeline | Triggered during document upload | `indexing_service.index_document_text()` | OCR text extract | Currently naive chunker; upgrading to regulation splitter | Vector store JSONL / Qdrant | Embedding provider | Falls back to local embeddings | **Needs Integration** |
| **Decision Path Optimizer** | `frontend/app/dashboard/decision-optimizer/page.tsx` | Select case, adjust weights sliders | `POST /api/v1/decision/optimize` | Case evidence, weights, days | `decision_engine.evaluate_candidates()` | Previously transient; migrating to case event persistence | None | Penalizes missing prerequisites | **Needs Case Integration** |
| **Knowledge Graph** | `frontend/components/3d/KnowledgeGraph` | Explore institution dispute patterns | `GET /api/v1/graph/stats` & `/query` | Case domain & institution | `knowledge_graph.get_stats()` | `neo4j_fallback.jsonl` / Neo4j | Neo4j service (optional, JSONL fallback) | Graceful offline graph fallback | **Real & Persistent** |

---

## 2. Identified Deficiencies & Remediation Plan

1. **Connector & Approval Ephemeral State**:
   - *Problem*: `ActionApprovalGate` and `AviationRefundConnector` stored records only in process memory (`self._operations`, `self._approved_tokens`). A server restart or multiple worker processes causes tokens and operations to vanish.
   - *Fix*: Back them by `LocalRepositoryStore` (`datasets/app_store/action_approvals.jsonl`, `datasets/app_store/connector_operations.jsonl`, `datasets/app_store/action_audit_log.jsonl`).

2. **Missing Real Outbound Delivery Connector**:
   - *Problem*: RECLAIM prepared appeal drafts, but lacked a real outward delivery connector to dispatch authenticated complaints to company customer care or statutory nodal officers.
   - *Fix*: Implement `EmailComplaintConnector` (`reclaim.connectors.email_delivery`) with SMTP / local test maildir outbox support, capturing real message IDs, timestamps, and attaching verified regulatory citations.

3. **RAG Ingestion Disconnect**:
   - *Problem*: `backend/app/rag/indexing/service.py` still invoked the old naive character splitter `chunk_text()`.
   - *Fix*: Wire `RecursiveRegulationTextSplitter` directly into `indexing_service.index_document_text()`, preserving section headings, statutory references, and character budget guarantees during document ingestion.

4. **Decision Engine Case Disconnect**:
   - *Problem*: The Decision Engine accepted ad-hoc parameter arrays rather than binding directly to a real persisted case ID and reading its actual documents and facts.
   - *Fix*: Enhance `/api/v1/decision/optimize` to accept a `case_id`, load actual case documents, automatically detect uploaded evidence (PNR, cancellation letter, rejection proof), compute utility, and append a `DECISION_OPTIMIZED` event to the case timeline.

5. **Frontend Case Linking**:
   - *Problem*: Connector and Decision pages operated with hardcoded mock IDs instead of letting users pick from their real saved cases.
   - *Fix*: Add a Case Selector dropdown in `/dashboard/connectors` and `/dashboard/decision-optimizer` that queries `/api/v1/cases`, populates real case telemetry, and saves actions to the real case.
