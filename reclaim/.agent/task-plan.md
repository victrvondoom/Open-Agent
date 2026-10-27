# RECLAIM Implementation Plan & Milestone Execution

## Milestones

### Milestone A — Baseline & Rebranding (Phase 1)
- [x] Pytest baseline execution (65 passed).
- [ ] Safe user-facing rebranding:
  - Product: RECLAIM
  - Tagline: "From problem to proof to resolution."
  - Announcement banner and card: "Introducing RECLAIM: Your rights shouldn't depend on knowing the right words..."
  - Retain backwards-compatible API routes and database identifiers.
  - Update `README.md`, `frontend/components/landing/Nav.tsx`, `Hero.tsx`, `Footer.tsx`, `Shell.tsx`, and Next.js metadata.

### Milestone B — Recursive, Regulation-Aware Text Splitter (Phase 3)
- [ ] Implement `RecursiveRegulationTextSplitter` in `backend/app/rag/regulation_splitter.py`.
- [ ] Implement API endpoint: `POST /api/v1/split` with character & token length calculation, metadata, source offsets.
- [ ] Comprehensive unit tests covering all 10 acceptance scenarios:
  1. Varied separator distribution
  2. Long paragraph without newlines
  3. Long uninterrupted token (empty string fallback)
  4. Text containing only questions
  5. Mixed English and Tamil (Unicode preservation)
  6. Statutory clauses with numbered subsections ("Section 3.2")
  7. Repeated text with overlap
  8. Empty/malformed inputs
  9. Table and legal citations
  10. Strict character budget enforcement
- [ ] Interactive Developer Inspector in frontend for splitting visualization.

### Milestone C — RECLAIM Action Fabric & Vertical Slice (Phase 2 & Phase 6)
- [ ] Implement `backend/app/services/connectors/base.py`:
  - `ConnectorManifest`, `ActionSpec`, `PreparedAction`, `ActionResult`, `ConnectorStatus`.
- [ ] Implement `backend/app/services/connectors/registry.py`:
  - Connector registration, capability discovery, health checks.
- [ ] Implement `backend/app/services/connectors/aviation_refund.py`:
  - Vertical slice: Airline flight cancellation & refund dispute (DGCA / EU261).
  - Dry-run validation, action preparation, approval token issuance, sandbox execution, reconciliation.
- [ ] Implement Action Approval Gate in `backend/app/services/connectors/approval_gate.py`:
  - Strict human approval check before any consequential external action is dispatched.
- [ ] Mount API routes: `GET /api/v1/connectors`, `POST /api/v1/connectors/{id}/prepare`, `POST /api/v1/connectors/{id}/approve`, `POST /api/v1/connectors/{id}/execute`, `GET /api/v1/connectors/{id}/status/{op_id}`.

### Milestone D — Regulatory Evidence Engine & Mathematical Decision Engine (Phase 4 & Phase 5)
- [ ] Implement `RegulatoryEvidenceEngine` with structured claim citations and verification states.
- [ ] Implement `ReclaimDecisionEngine` with multi-objective utility scoring and constraint evaluation.
- [ ] API routes: `POST /api/v1/decision/optimize` to rank dispute resolution paths (e.g. Direct Refund -> Escalation -> Regulatory Filing).

### Milestone E — Build with AI: Basics Submission Boundary (Phase 9)
- [ ] Create `scope.md`, `prd.md`, and `spec.md` with complete, rigorous specifications.
- [ ] Document the clear boundary between the competition MVP vertical slice and the platform vision.

### Milestone F — Frontend User Experience & Verification (Phase 7 & Phase 8)
- [ ] Implement Action Approval Center & Connector Registry in Frontend.
- [ ] Implement Text Splitter Developer Inspector in Frontend.
- [ ] Implement Decision Engine Path Optimizer in Frontend.
- [ ] Verify complete backend pytest suite.
- [ ] Verify Next.js build.
- [ ] Produce final 10-point Master Engineering Delivery Report.
