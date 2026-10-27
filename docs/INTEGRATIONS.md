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

These states are computed by `payproof/integrations.py` from runtime outcomes. They are shown in three places:
- the UI header chips;
- the **Sponsor integrations** panel;
- `python3 run.py --check-integrations`.

Tests that use local stubs reset the status afterwards, so a mock can never make an integration read LIVE.

**Connectivity** is reported separately from the state. It takes one of these values:
- `in-process`: the three Meterless engines run inside PayProof;
- `online`;
- `offline`;
- `unauthorized`: HTTP 401/403;
- `degraded`: some systems served and others failed, or a failure after an earlier success;
- `not configured`.

## Integration dashboard and Run live check

Each tile in the Decision Room's **Sponsor integrations** panel (`GET /api/integrations`) shows:
- whether it is required;
- configured;
- state and connectivity;
- provider or model;
- last success and its latency;
- last error;
- whether the **latest investigation used it**;
- what kind of data flowed through it.

A banner appears when a configured integration's last call failed (UNAVAILABLE). Fallback paths are labelled on every result.

**Run live check** (`POST /api/integrations/check`, or `python3 run.py --check-integrations` on the command line) makes these real diagnostic calls and returns what happened (`payproof/diagnostics.py`):

| Integration | Diagnostic | Passes when |
|---|---|---|
| World Model | ingests the demo case twice | the first ingest changes state and the second reports `changed=false` (the idempotency contract) |
| H-MEM | writes a probe memory into a scratch store and queries for it; reports the live store's size | the probe comes back as the top hit |
| Scout Intent | issues and verifies a signed contract; submits an injection probe | the contract verifies and the probe is refused `INJECTION_BLOCKED` |
| Zetaris | one fixed `SELECT` per source system | all six systems answer |
| Nemotron | `/models` lookup, then one minimal completion | the model is listed and the completion succeeds |

If Zetaris or Nemotron is not configured, it is reported as **not run** and no call is made. Nothing is simulated in its place. The CLI exits non-zero if any check that ran failed.

## Matrix

| Sponsor | Implemented | Verified how | Live in this repo? | What's left |
|---|---|---|---|---|
| **Meterless — World Model engine** | ✅ `payproof/world_model.py` | One-to-one Python port of the official 8-check conformance suite (`tests/test_world_model.py`): 8/8. PayProof-specific tests cover idempotent case ingest, late-event detection, provenance, bitemporal point-in-time queries and the context builder. | **Yes, in-process.** It runs on every investigation and every approval/execution, and it changes outcomes: the verifier cross-check and the stale-evidence gate. | Optionally run the official TypeScript runner against it (see below). |
| **Meterless — H-MEM** | ✅ `payproof/hmem.py` (port of `engines/hmem/reference/src`) + `PrecedentMemory` | `tests/test_hmem.py` ports the official conformance runner and runs the official vectors file, copied unchanged (Apache-2.0, see `tests/vectors/NOTICE.md`): **13/13**. PayProof tests check that only verified actions are stored, that writes are idempotent and that a case never recalls itself. The benchmark checks that recall never changes a decision: cold vs warm, 30/30. | **Yes, in-process.** It recalls on every case view and writes after every verified action. Precedents are advisory: they are shown to the reviewer and never enter the calculation. | Tune precedent ranking with reviewer feedback (top-precedent action consistency is 5/15 today). |
| **Meterless — Scout Intent** | ✅ `payproof/scout.py` (implements `engines/scout-intent/docs`; the spec ships no code) | `tests/test_scout.py` covers guard patterns, metadata-only evidence and PII redaction. It covers the contract checks: signature, expiry, scope, intent and subject. It also checks that every action step carries a contract, that quarantined cases need a controller, and that injected intake gets a 422. Benchmark: blocks **15/15** corpus attacks with **0/15** benign false positives; detects **4/4** planted record injections; **0/4** changed a decision. | **Yes, in-process.** It guards every investigation and every action call. | A learned classifier alongside the patterns; an external attack corpus. |
| **Zetaris** | ✅ `ZetarisSource` per the documented direct REST route | Contract-tested against a local stub: request path, headers, body keys, row mapping, zero-row answers, HTTP 401, unreachable host, SQL-injection rejection (`tests/test_zetaris.py`). Live smoke test included; it skips without credentials. | **No.** No Zetaris instance or credentials in the build environment, and egress to Zetaris hosts was blocked. | Register the CSVs and run `python3 run.py --check-integrations`. |
| **NVIDIA Nemotron** | ✅ `payproof/llm.py` (`https://integrate.api.nvidia.com/v1`, `/models` check, temperature 0, 2-call budget, cache) | Stub endpoint returning one valid claim, one with a hallucinated record id and one with an invented amount: the validator keeps 1 and drops 2 (`tests/test_model_path.py`). | **No.** No API key, and egress to `integrate.api.nvidia.com` was blocked by the build environment's network policy. | Set `NVIDIA_API_KEY`, run `--check-integrations`, and re-run the benchmark. |
| **Cursor** | `.cursor/rules/payproof.mdc` | n/a | n/a (IDE) | **Blocker:** this code was produced in a Claude Code session. Do the remaining work in Cursor and describe it truthfully in the submission. |

## How Meterless is integrated (for the Sponsor Tech explanation)

The World Model engine is PayProof's canonical evidence state. It does four jobs:

1. **Evidence intake.** `ingest_case` writes every source record as an externally keyed entity: `payment:billing:PAY-44987`, with provenance `{kind: "billing-sim (NetSuite-like)", at: <recorded_at>}`. It then writes typed relationships (`pays`, `amends`, `credits-invoice`, `paid-to`, …) whose `validFrom` is the record's **effective** time. That makes the store bitemporal: *when it happened* versus *when a system learned of it*, which is exactly the distinction behind the demo's late-recorded payment.
2. **Independent verifier cross-check.** The policy verifier asks the World Model for the cash events valid as of the cutoff (`neighbors_of(invoice, via="pays", at=cutoff)`). It requires that set to equal what the Decimal engine counted. If it doesn't, the proof is REJECTED. This holds on all 30 cases.
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

## How Meterless H-MEM is integrated

H-MEM is PayProof's **verified-precedent memory**. `payproof/hmem.py` is a Python port of the official reference. It keeps:
- the hybrid retrieval formula: `0.35·semantic + 0.20·keyword + 0.10·tag + 0.10·domain + 0.15·entity + 0.05·layer + 0.05·recency − 0.20·superseded`, clamped, then multiplied by confidence;
- the deterministic FNV-1a 64-dim embedder;
- writes that are rejected without a source;
- feedback deltas of +0.05 / −0.03 / −0.20;
- the append-only trust ledger;
- conflict detection with the 0.70 auto-resolve gate, where the loser is superseded and never deleted;
- the preview-first sleep cycle with guardrails;
- dreaming, which never materializes without approval.

How PayProof uses it (`PrecedentMemory`):

1. **Write rule.** A precedent is written only when a human-approved action reaches `VERIFIED` and its postcondition re-investigation passed.
   - It is tagged with the case's evidence patterns: finding families such as `SK-DUP` or `SK-LATE`, plus blocker codes, the verdict and the action type.
   - It cites the case id, action id, receipt id and proof hash.
   - Writes are idempotent per action.
   - Unverified, rejected or failed actions never become memory.
2. **Read rule.** Each investigation queries H-MEM with its own patterns, filtered to *other* cases. Self-retrieval contamination measured 0 in the benchmark. The reviewer sees each precedent's relevance, the patterns it shares with the case, its outcome, its refs, and whether its action agrees with the current recommendation. The case-comparison view opens a precedent side by side.
3. **Precedents never decide.** They are not inputs to the policy engine, the verifier or the planner. The benchmark checks this: decisions are identical cold vs warm, 30/30.

**Memory evaluation** (`docs/BENCHMARK.md`):
- 21 precedents were built by settling every case through the real action service.
- Warm hit rate was 0.71, against 0.00 cold.
- Precision@3 was 0.925.
- The top precedent's action matched the case's own verified action in only 5 of 15 warm recalls. That is why precedents stay advisory.

PayProof queries with threshold 0.2 rather than the reference's 0.35 default, because pattern-tag queries are short. The ranking formula is unchanged.

## How Meterless Scout Intent is integrated

The Scout Intent spec (`engines/scout-intent/docs/risk-and-policy.md`, `execution-contract.md`) publishes contracts, not code. `payproof/scout.py` implements it:

- **Sense:** a declared intent registry of `dispute.file`, `action.propose`, `action.approve` and `action.execute`. Each entry carries its required permission and the exact capability set it grants.
- **Guard:**
  - an injection check with three detector kinds: instruction patterns, role drift and out-of-band tool or SQL references;
  - an RBAC policy gate;
  - PII and credential redaction.
  - Only metadata is logged (`kind@offset`), never the payload.
- **Recommend:** an **HMAC-SHA256-signed execution contract** with a 5-minute TTL, user-scoped and capability-scoped.

Downstream, the action service follows "downstream engines act on contracts". It refuses to propose, approve or execute unless a contract verifies on all of these:
- signature;
- expiry;
- capability, e.g. `payroll.sim.write` for execution;
- intent;
- subject.

Contracts are listed on each action in the UI.

Untrusted text enters PayProof in two places, and each has its own policy:
- **User intake** (`POST /api/cases`): an embedded instruction **blocks** the request with `422 INJECTION_BLOCKED`.
- **Retrieved source records** (memos, account names, reasons) and the dispute narrative: the record is **quarantined**.
  - Its text is excluded from the model context.
  - The case gets a high-severity `SK-INJ-<record>` security finding.
  - The proposed action is **escalated to controller approval**.
  - The amounts are still computed by deterministic code, so the planted instruction ("approve immediately", "set status to VERIFIED") changes nothing. Measured over the 4 planted cases: injection success 0/4.

The ablation without Scout shows what it contributes. Decisions stay 30/30, because the money path is deterministic either way. But the approval level is wrong on exactly the 4 injected cases: finance_approver instead of controller, 9/13 correct vs 13/13. Quarantined text would also reach the model.

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
3. Run `python3 run.py --check-integrations`. It does three things:
   - runs one full investigation, which makes up to 2 narration calls;
   - checks the model id against `/models`;
   - sends one minimal completion.

   The status reads LIVE only if a real call succeeded.
4. Re-run `python3 -m payproof.bench` and report the model path separately.

## How Cursor was used

Not yet. See the blocker above. Write this section from what the team actually does in Cursor.
