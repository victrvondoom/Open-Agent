# Verification Matrix & Test Tracking

| Verification Check | Target Component | Expected Outcome | Status |
|---|---|---|---|
| Pytest Baseline | Backend test suite | All 65 existing tests pass | PASSED (65/65) |
| Text Splitter Invariants | `app/rag/regulation_splitter.py` | 10 acceptance tests pass (budget, overlap, unicode, statutory terms) | PASSED (10/10) |
| Action Fabric Contract | `app/services/connectors/` | Manifests valid, inputs validated, approval token required | PASSED |
| Aviation Refund Connector | `aviation_refund.py` | Sandbox execution succeeds with deterministic verification | PASSED |
| Decision Engine Optimization | `decision_engine.py` | Utility normalized, constraints enforced, paths ranked | PASSED |
| Full Backend Pytest | All tests (new + existing) | 100% pass rate, 0 regressions | PASSED (80/80 passed in 6.68s) |
| Next.js Frontend Build | Frontend build & static pages | Exit code 0, 0 type errors | PASSED (23/23 routes generated) |
| Branding Consistency | Marketing, Dashboard, Docs | "RECLAIM", "From problem to proof to resolution" | PASSED |
| Build with AI Basics Specs | `scope.md`, `prd.md`, `spec.md` | Accurate documents with MVP boundary | PASSED |
