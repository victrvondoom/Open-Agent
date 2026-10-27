# Submission checklist — Open Agent Hackathon 2026

Submit on **HackOS** before **27 October 2026, 23:45 UTC** (hard deadline). Requirements are from the organizer Submission Requirements and Disqualification Checklist; see `docs/INTEGRATIONS.md` for sources.

## Unified Platform: RECLAIM × Open-Agent — Evidence-Verified Dispute Resolution OS

| Item | Status | Where |
|---|---|---|
| Public GitHub repo with README (setup, usage, dependencies) | ✅ Updated | `https://github.com/victrvondoom/Open-Agent` (branch: `feature/unified-reclaim-openagent`) |
| Live unified frontend (Decision Room) | ✅ Operational | `web/` served on `http://127.0.0.1:8360` with Dark Charcoal & Warm Cream themes |
| Server-to-Server Integration | ✅ Operational | `payproof/reclaim_bridge.py` connecting to RECLAIM FastAPI backend on `http://127.0.0.1:8001/api/v1` |
| Sponsor technology explanation & diagnostics | ✅ Verified | `docs/INTEGRATIONS.md`, `payproof/diagnostics.py` |
| Sample inputs and outputs (≥3) and audit traces | ✅ Operational | `samples/`, `var/cases/`, live hash-chained audit log at `/api/audit` |
| Mandatory human sign-off & sandbox execution | ✅ Enforced | RBAC approval controls with tamper-evident receipts (`RCPT-RECLAIM-...`) |
| Automated test suite | ✅ 97 Tests Passing, 1 skipped | `python -m unittest discover -s tests` (76 baseline PayProof + 22 RECLAIM bridge/verifier; the skip is the live Zetaris smoke test) |
| `.env.example` with placeholders | ✅ Configured | `.env.example` |

## Sponsor Integrations Status

1. **Meterless (LIVE in-process):**
   - **World Model:** Bitemporal entity-fact graph, state shape hashing (16-hex canonical hash), and state invalidation gates. Conformance suite: 8/8 passing.
   - **H-MEM:** Precedent memory recall over verified outcomes. Vector conformance: 13/13 passing.
   - **Scout Intent:** Prompt-injection quarantine, permission checks, and HMAC-signed execution contracts.
2. **RECLAIM Multi-Agent Backend (LIVE):**
   - Connects to running FastAPI service on port 8001 (`/api/v1/agents/run-case`, `/api/v1/cases`).
   - Consumer disputes across 8 RECLAIM domains (IRDAI, DGCA, RBI, RERA, TRAI, CCPA). The deterministic verifier decides airline cancellations only, against DGCA CAR and RBI UPI rules; other domains abstain for human review.
3. **Zetaris Federated SQL (CONFIGURED / FALLBACK):**
   - Parameterized, allowlisted SQL queries for both payroll records and consumer dispute evidence (`consumer_transactions`, `consumer_refund_records`, `consumer_policy_records`, `consumer_case_events`).
   - Local synthetic fixtures active; live smoke test skips cleanly when credentials are unconfigured.
4. **NVIDIA Nemotron (CONFIGURED / FALLBACK):**
   - Evidence-constrained explanation engine citing allowlisted record IDs and regulatory clauses.
   - Preserves deterministic fallbacks when API keys are absent; labeled accurately in diagnostics.
5. **Cursor:**
   - Development environment and configuration rules documented.

## Form Fields & Pre-Existing Component Disclosure

- **Track:** 02, The Agent That Can Explain Why (with multi-domain dispute reasoning).
- **Pre-existing components disclosure:**
  - **Existing in RECLAIM:** Consumer dispute intake, FastAPI backend with 8 Indian consumer dispute domains, LangGraph multi-agent orchestrator, statutory datasets, and Next.js frontend.
  - **Existing in Open-Agent:** PayProof deterministic commission engine, 30 synthetic benchmark cases, 76 baseline unit tests.
  - **New Integration Built for Hackathon:** Server-to-server HTTP integration bridge (`payproof/reclaim_bridge.py`), regulatory citation verification & contradiction detection (`payproof/reclaim_evidence.py`), unified Meterless bitemporal verification adapter (`payproof/reclaim_verifier.py`), extended Zetaris SQL adapter for consumer dispute tables, unified Dark Charcoal & Warm Cream 3-column Decision Room UI (`web/`), dual dispute intake modal with simulated Wispr voice input, RBAC sandbox action approval receipts (`RCPT-RECLAIM-...`), and 22 new bridge/verifier tests (total 98 tests).
- **Roster:** Confirm team members before submitting.

## Final Checks Before Pressing Submit

- [x] Run both services: RECLAIM on port 8001, Open-Agent on port 8360
- [x] Test suite passing: `python -m unittest discover -s tests` (97 passing, 1 skipped)
- [x] Benchmark runner verified: `python -m payproof.bench`
- [x] Diagnostics clean: `python run.py --check-integrations`
- [x] No secrets or API keys hardcoded in repo
- [x] Honest sponsor status: Meterless and RECLAIM are LIVE; Zetaris and Nemotron report FALLBACK/CONFIGURED

