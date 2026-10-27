# Sponsor technology: integration matrix and explanation

## Requirements (organizer sources)

These come from the organizer documents (Official Rules, Submission Requirements, Disqualification Checklist and sponsor overviews). The official site wasn't reachable from the build environment, so they were read from a participant's public mirror ([arunsanna/open-agent-hackathon-2026](https://github.com/arunsanna/open-agent-hackathon-2026), `hackathon-metadata/resources/`). Re-check the event page before submitting.

| Sponsor | Rule |
|---|---|
| Zetaris | **Required:** every submission must integrate Zetaris |
| Meterless | **Required:** every submission must integrate Meterless. "Meaningful use counts toward Sponsor Tech"; say which engines you used and where (README and `metadata.json`) |
| Cursor (with Space XAI) | **Required:** teams must use Cursor as their development environment (also on the disqualification checklist) |
| NVIDIA | Integrate wherever it contributes |

The deadline is **27 October 2026, 23:45 UTC, on HackOS**. Deliverables are a 1–4 min demo video, a slide deck covering 8 points, a public GitHub repo with README, and the sponsor explanation. A public deployment is **not** required. Judges run the project themselves.

Meterless Nightshift is **not** a stated requirement in these documents. The Meterless sponsor docs describe the engines as "reference architectures, not a library you `pip install`. You implement the services described, in whatever language/framework your agent uses."

## Status legend (runtime truth)

| State | Meaning |
|---|---|
| LIVE | a real execution or request succeeded in this process |
| CONFIGURED_UNVERIFIED | configured, but no successful call yet |
| FALLBACK | not configured; the local or simulated path is in use |
| UNAVAILABLE | configured, and the last attempt failed with no success since |

These states are computed by `payproof/integrations.py` from runtime outcomes and shown in the UI header and by `python3 run.py --check-integrations`. Tests that use local stubs reset the status afterwards, so a mock can never make an integration read LIVE.

## Matrix

| Sponsor | Implemented | Verified how | Live in this repo? | What's left |
|---|---|---|---|---|
| **Meterless — World Model engine** | ✅ `payproof/world_model.py` | One-to-one Python port of the official 8-check conformance suite (`tests/test_world_model.py`): 8/8. PayProof-specific tests cover idempotent case ingest, late-event detection, provenance, bitemporal point-in-time queries and the context builder. | **Yes, in-process.** It runs on every investigation and every approval/execution, and it changes outcomes: the verifier cross-check and the stale-evidence gate. | Optionally run the official TypeScript runner against it (see below). |
| **Zetaris** | ✅ `ZetarisSource` per the documented direct REST route | Contract-tested against a local stub: request path, headers, body keys, row mapping, zero-row answers, HTTP 401, unreachable host, SQL-injection rejection (`tests/test_zetaris.py`). Live smoke test included; it skips without credentials. | **No.** No Zetaris instance or credentials in the build environment, and egress to Zetaris hosts was blocked. | Register the CSVs and run `python3 run.py --check-integrations`. |
| **NVIDIA Nemotron** | ✅ `payproof/llm.py` (`https://integrate.api.nvidia.com/v1`, `/models` check, temperature 0, 2-call budget, cache) | Stub endpoint returning one valid claim, one with a hallucinated record id and one with an invented amount: the validator keeps 1 and drops 2 (`tests/test_model_path.py`). | **No.** No API key, and egress to `integrate.api.nvidia.com` was blocked by the build environment's network policy. | Set `NVIDIA_API_KEY`, run `--check-integrations`, and re-run the benchmark. |
| **Cursor** | `.cursor/rules/payproof.mdc` | n/a | n/a (IDE) | **Blocker:** this code was produced in a Claude Code session. Do the remaining work in Cursor and describe it truthfully in the submission. |

## How Meterless is integrated (for the Sponsor Tech explanation)

The World Model engine is PayProof's canonical evidence state. It does four jobs:

1. **Evidence intake.** `ingest_case` writes every source record as an externally keyed entity: `payment:billing:PAY-44987`, with provenance `{kind: "billing-sim (NetSuite-like)", at: <recorded_at>}`. It then writes typed relationships (`pays`, `amends`, `credits-invoice`, `paid-to`, …) whose `validFrom` is the record's **effective** time. That makes the store bitemporal: *when it happened* versus *when a system learned of it*, which is exactly the distinction behind the demo's late-recorded payment.
2. **Independent verifier cross-check.** The policy verifier asks the World Model for the cash events valid as of the cutoff (`neighbors_of(invoice, via="pays", at=cutoff)`). It requires that set to equal what the Decimal engine counted. If it doesn't, the proof is REJECTED. This holds on all 25 cases.
3. **Context builder.** The Nemotron prompt is built from the World Model neighbourhood of the disputed opportunity, so the model sees provenance-stamped entities rather than a raw dump.
4. **Stale-evidence gate.** Each proposed action captures its own World Model snapshot. Approval and execution re-ingest the current sources. By the engine's idempotency contract, an unchanged batch reports `changed=false`, so `changed=true` expires the action before any money moves. The sha256 source fingerprint is a second, independent signal; the two are recorded side by side and must agree.

The World Model audit is written as JSONL under `logs/` for every case viewed, and under `samples/logs/` for the samples.

**What's unique about this use.** The bitemporal edges carry PayProof's core financial distinction: value date versus recorded date. The engine's idempotency contract becomes a *payroll safety control* instead of just a data-hygiene property.

**Run the official conformance runner yourself (optional, not done in the build environment):**

```bash
npx degit meterless/meterless/engines/world-model /tmp/wm && cd /tmp/wm/reference && npm install
npx tsx ../conformance/runner.ts    # reference: should be 8/8
# The runner loads a TypeScript module, so checking the Python engine requires a bridge; not provided.
```

## How Zetaris is integrated

- **Route.** This is the documented direct REST route from `zetaris/getting-started` (`scripts/zetaris_sql.py`, `RestChannel`): `POST {ZETARIS_REST_URL}/sql-editor/sqls/run`, headers `Authorization: Bearer <API key>`, `X-Org-ID`, `X-Request-ID`, body `{queryId, sql, source: "SqlEditor", limit}`, and rows returned in `data`.
- **SQL.** One fixed template per source system: `SELECT record_id, record_type, payload_json FROM {db}.{system}_records WHERE case_key = '{case}' ORDER BY record_id`. No bind parameters are documented for this route, so the only interpolated values are a database identifier and a case key, both regex-validated. Model or user text never reaches SQL.
- **Mapping and provenance.** `payload_json` is the original record. Rows whose payload id or type disagrees with `record_id` or `record_type` are rejected. Provenance per system is `zetaris`, `zetaris (0 rows)` or `fixture-fallback (<reason>)`, and it is shown in every investigation.
- **Failure handling.** HTTP errors, timeouts and unreachable hosts fall back per system. Error bodies are not echoed into logs.

**Setup:**

1. Run `python3 scripts/export_zetaris_csv.py`, which writes `data/zetaris/<system>_records.csv`.
2. Make those files reachable from your Zetaris instance. Replace `<PATH>` in `docs/zetaris/register.sql` and run it. It is written to the Lightning SQL reference syntax but has not been run.
3. Set `ZETARIS_REST_URL`, `ZETARIS_API_KEY` and `ZETARIS_ORG_ID`.
4. Run `python3 run.py --check-integrations` and `python3 -m unittest tests.test_zetaris`. The live smoke test runs automatically when credentials are present.

## How NVIDIA is used

Nemotron phrases two things: the resolution explanation and the skeptic's strongest counterargument. It never computes amounts, never sets status and never authorizes anything. The validator drops any sentence that cites an id outside the evidence index, or that contains an amount the engine didn't compute.

**To validate:**

1. Set `NVIDIA_API_KEY=nvapi-…`.
2. Set `LLM_MODEL` to the exact id from build.nvidia.com. The default is `nvidia/nemotron-3-ultra-550b-a55b`, which is unverified.
3. Run `python3 run.py --check-integrations`. It lists the Nemotron ids from `/models` and makes one narration call. The status reads LIVE only if the call succeeded.
4. Re-run `python3 -m payproof.bench` and report the model path separately.

## How Cursor was used

Not yet. See the blocker above. Write this section from what the team actually does in Cursor.
