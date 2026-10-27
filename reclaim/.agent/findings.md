# RECLAIM — Investigation Findings & System State

## 1. Architectural Baseline
- **Backend**: FastAPI 0.115 with Python 3.12, Pydantic v2 settings, async endpoints.
- **Agent Orchestrator**: LangGraph-based workflow (`LangGraphWorkflow` / `RoleAgents`) coordinating Planner, Retrieval, Knowledge Graph, Web Search, Evidence (OCR), Strategy, Negotiation, Review, and Response agents.
- **RAG & Storage**:
  - Vector store: Qdrant with local JSONL fallback mode (`vector_store_backend: "jsonl"`).
  - Knowledge graph: Neo4j with local JSONL fallback mode (`graph_store_backend: "jsonl"`).
  - Storage: Local filesystem document vault with OCR pipeline (`tesseract` / fallback).
- **Frontend**: Next.js 15.5 with React 19, TypeScript, Tailwind CSS, Framer Motion, and WebGL SceneBackground.
- **Domain Coverage**: 8 regulated domains: Healthcare, Airlines, Banking, Telecom, E-commerce, Housing (RERA), Government, and Insurance.

## 2. Test Baseline & Health
- Pytest suite: 65 passing unit and integration tests across API, auth, model routing, OCR, vector store, and LLM providers.
- Next.js build: Clean compilation of all 20 static and dynamic routes.

## 3. Key Evolution Targets (From RESOLVE to RECLAIM)
1. **Rebranding**: Transition user-facing surfaces to RECLAIM with the tagline: *"From problem to proof to resolution."*
2. **Action Fabric (Connector Layer)**:
   - Implement an extensible connector registry independent of Switch.
   - Deliver vertical slice: Flight Booking & Cancellation Dispute with refund claim execution via deterministic, verifiable connector.
   - Implement human-in-the-loop Action Approval Gate before any consequential action is taken.
3. **Recursive, Regulation-Aware Text Splitter**:
   - Multi-separator fallback chain: `["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]`.
   - Preserve legal identifiers (e.g., "Section 3.2", acts, clauses, numbered lists).
   - Character/token constraints (200 char default for interactive demo, 20 char overlap).
   - Complete metadata: offsets, parent sections, language, hashes.
4. **Regulatory Evidence Engine**:
   - Structured claim verification references with authoritative provenance and verification states (`source_found`, `source_identity_established`, `passage_matched`, `interpretation_supported`, etc.).
5. **Reclaim Decision Engine (Mathematical Optimization)**:
   - Multi-objective utility model: $U(a) = w_1 B(a) - w_2 C(a) - w_3 D(a) - w_4 R(a) - w_5 P(a)$.
   - Constraint-aware evaluation (deadlines, documentation requirements, reversibility).
6. **Build with AI: Basics Documentation**:
   - `scope.md`, `prd.md`, and `spec.md` documenting the MVP vertical slice and long-term operating system boundary.
