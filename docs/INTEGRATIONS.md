# Sponsor integration matrix

Requirements below are as relayed in a public participant tracker of the organiser Q&A ([JannetEkka/DSProjects#23](https://github.com/JannetEkka/DSProjects/issues/23)). The official site (hackathon.genai.works) wasn't reachable from the build environment, so **re-check against the official rules before submitting.**

- Meterless: "at least one Meterless Engine working in a real feature" (H-MEM, World Model, Markovian or Scout Intent). "A mention or an unused dependency doesn't count."
- Meterless Nightshift must be the app's AI provider, with Nemotron behind it through an NVIDIA key.
- Zetaris runs locally in Docker.
- Cursor must be used for development. "Claude Code alongside Cursor is OK."
- Deliverables: a 1–4 min video, a deck, the repo with README, and how each sponsor's tech was used. Deadline Oct 27, 23:45 UTC.

| Sponsor | Required | Implemented | Tested | Mode now | Notes |
|---|---|---|---|---|---|
| NVIDIA Nemotron | yes | ✅ `payproof/llm.py` (OpenAI-compatible chat completions, temperature 0, JSON claims, 2-call budget) | ✅ against a **local stub** (`tests/test_model_path.py`) — **not against live Nemotron** | fallback | Set `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Model identity and latency are recorded per call in `telemetry.model_calls`. |
| Meterless Nightshift | yes | ✅ same client; `LLM_PROVIDER=nightshift`, `LLM_BASE_URL=<Nightshift endpoint>` | ❌ | not configured | Nightshift has no Linux edition, so it couldn't run in the build container. The exact endpoint and port must come from the Nightshift app. |
| Meterless Engine | yes | ⚠️ adapter `payproof/meterless.py` (World Model ranks counterfactual scenarios; advisory only) | ❌ | fallback (deterministic impact ranking) | **The HTTP route `/v1/engines/{engine}/rank` is an assumption.** Replace it with the real engine API on a machine running Meterless. Until then, this requirement is **not met**. |
| Zetaris | yes | ⚠️ adapter `payproof/sources.py: ZetarisSource` with six allowlisted, parameterised templates (`ZETARIS_QUERIES`) and per-system fallback plus provenance | ❌ | fallback (local fixtures) | Register the synthetic fixtures as Zetaris tables (`docs/zetaris/register.sql`) and adjust the `/query` request shape to the Zetaris REST API. The UI shows per-system provenance (`zetaris` vs `fixture-fallback`). |
| Cursor | yes | `.cursor/rules/payproof.mdc` | n/a | n/a at runtime | This repository was built in a Claude Code session. The team must do development work in Cursor themselves to satisfy the rule. Cursor is an IDE, not a runtime integration. |

## Steps to close the blockers (on a Mac or Windows machine with the sponsor tools)

1. Install Meterless Nightshift, add the NVIDIA key, and enable a Nemotron model. Copy its OpenAI-compatible base URL, then run `LLM_PROVIDER=nightshift LLM_BASE_URL=... python3 -m payproof.server`. Open CASE-1001 and confirm the header chip reads `NVIDIA Nemotron: live`, the run-provenance panel lists the model id, and model calls show `ok`.
2. Read the Meterless engine docs and update `meterless.rank_scenarios` to the real request/response. Then set `METERLESS_URL` and confirm `scenario ranking: meterless ok`.
3. Start the Zetaris Docker bundle, load `data/cases/*.json` into the tables named in `ZETARIS_QUERIES`, and set `ZETARIS_URL`. Confirm the sources line in run provenance shows `zetaris` for each system.
4. Re-run `python3 -m payproof.bench` with the live model and commit the new report. The validator will count any unsupported claims the live model produces.
