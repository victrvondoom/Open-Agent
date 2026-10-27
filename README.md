# PeoplePay-360 · PayProof

**Proof-carrying commission dispute resolution.** A sales rep says they were underpaid. The CRM, contract system, billing, comp plan and payroll all disagree. PayProof works out **what should have been paid**. It shows which evidence establishes that figure and which alternative explanations it tested. It also says what is still uncertain and **what exact action is safe to take next**. Any action needs a backend-enforced approval, and the system verifies the result after execution.

> Built for the GenAI.Works Open Agent Hackathon 2026 (Track 02 fit: *The Agent That Can Explain Why*).
> All people, companies and amounts are **synthetic**. No real money moves. Every execution goes to a **simulated** adapter.

## Quick start (no credentials, no dependencies)

Requires Python ≥ 3.10. There is nothing to install.

```bash
git clone https://github.com/victrvondoom/Open-Agent && cd Open-Agent
python3 -m payproof.server          # → http://127.0.0.1:8360
```

```bash
python3 -m unittest discover -s tests   # 23 tests: money, ground truth, authz, idempotency, stale evidence, model path
python3 -m payproof.bench --smoke       # 5-case smoke benchmark (≈0.2 s)
python3 -m payproof.bench               # full 25-case benchmark → bench/results/latest.json + docs/BENCHMARK.md
python3 scripts/build_fixtures.py       # regenerate synthetic source snapshots (optional)
```

Docker alternative: `docker build -t payproof . && docker run -p 8360:8360 payproof`.

Optional sponsor integrations are configured through environment variables (see `.env.example`). With none set, every integration reports **fallback** in the UI header. The app never claims a live integration that isn't running.

## The demo case (CASE-1001)

Maya Chen disputes a **$3,000** shortfall on Northwind Logistics. The CRM shows **$60,000** at 10%, so she expects $6,000. The engine finds:

| Fact | Source | Effect |
|---|---|---|
| Amendment AMD-3301-1 cuts the contract to $50,000 (signed before cutoff) | CLM | eligible value $50,000 |
| Invoice INV-8801 is partially paid: $36,000 + $9,000 | Billing | PAY-44987 was **recorded after the cutoff** but has a value date before it |
| Credit note CN-0077 of $2,000 | Billing | net collected **$43,000** |
| Plan v1 rate 10% (P-4.1) | Comp | due **$4,300.00** |
| Payroll: $3,600 commission, then CN-0077 clawed back **twice** (PL-…-041, PL-…-042) | Payroll | paid **$3,200.00** |

**Result:** VERIFIED. The claim is *partially supported*: the verified underpayment is **$1,100.00**, not $3,000. That figure is $900 of commission on the late-recorded payment plus $200 from reversing the duplicate clawback.
**Skeptic's strongest counterargument:** "PAY-44987 was recorded on 2026-07-03, after the cutoff. If it is excluded, she is owed only $200." The verifier tests this through counterfactual replay, then rules it out under clause **P-4.2** (value date governs).
**Action:** `PREPARE_PAYROLL_ADJUSTMENT $1,100.00`. It needs `finance_approver`. Segregation of duties applies: the proposer can't approve, and neither can the rep. The rep's approval attempt returns **403**. After approval, payroll-ops executes once on the simulated ledger. The postcondition then re-investigates the case and confirms paid = $4,300 and variance = $0. A hash-chained audit receipt is issued.

**Negative case (CASE-1015):** the rep asks for $4,500 now, but there is no contract in CLM. Status is **NEEDS_EVIDENCE**. The only action offered is `REQUEST_EVIDENCE`, which moves no money. A labelled *hypothetical* counterfactual shows what a contract would establish, without treating it as fact.

Demo walkthrough: [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

## Five core mechanisms

1. **Temporal identity and evidence graph** (`payproof/evidence.py`). Each fact keeps its source system, record id, effective time, recorded time and transformation history. HRIS↔CRM identity resolves only on an email or a recorded alias. Name-only matches are never merged: they are shown as candidates and the case becomes NEEDS_EVIDENCE.
2. **Proof-carrying decisions** (`payproof/workflow.py: build_bundle`). Each material claim carries supporting and contradicting records, policy clauses, plan version, calculation steps, assumptions and open questions. Its status is one of `VERIFIED | DISPUTED | NEEDS_EVIDENCE | REJECTED`. The run id, proof hash and source fingerprint make the result reproducible.
3. **Counterfactual payout replay** (`payproof/counterfactual.py`). Scenarios are derived from the facts in each case: recorded-date timing, full payment, a credit note on the other side of the cutoff, a voided or late amendment, split misattribution, duplicate removal and exception approval. Each one is replayed through the same deterministic engine. All are labelled `hypothetical` and never written back.
4. **Adversarial workflow with a deterministic verifier.** The workflow runs Investigator → Skeptic → Policy verifier → Resolution planner → Final validator. It is a fixed pipeline with at most 2 model calls. The verifier recomputes every number from the cited records, checks invariants, and decides whether a conflict is *material* by recomputing under each alternative. CASE-1010 is a material conflict, so it is DISPUTED. CASE-1011 is immaterial, so it is VERIFIED.
5. **Approval-gated actions** (`payproof/actions.py`). The state machine is `PROPOSED → VALIDATED → AWAITING_APPROVAL → APPROVED → EXECUTED → VERIFIED`, plus `REJECTED / FAILED / EXPIRED`. Authorization, approval limits, segregation of duties, idempotency keys, a 24 h approval TTL and source-fingerprint re-checks all run in the backend at both approval and execution. The adapter is simulated and also idempotent. Postconditions are verified by re-investigating the case.

**The model never touches money.** Nemotron, when configured, only phrases explanations. Each sentence it returns must cite record ids that exist in the case. Each dollar amount must match a value the engine computed. Anything else is dropped and counted (see `tests/test_model_path.py`).

## Benchmark (actual results)

Source: `python3 -m payproof.bench` (25 synthetic cases, hand-labelled ground truth in `bench/ground_truth.json`). The full report is in [`docs/BENCHMARK.md`](docs/BENCHMARK.md).

| Metric | PayProof | Rules-only baseline |
|---|---|---|
| Decision accuracy (status + verdict + action, + amount when money moves) | 25/25 | 11/25 |
| Exact due amount | 20/20 | 11/20 |
| Wrong payroll adjustments recommended | 0 | 10 |
| Correct abstention when evidence is missing or contradictory | 5/5 | 0/5 |
| Citation coverage of material claims | 100% | 0% |
| Unauthorized approvals/executions succeeded | 0 / 151 attempts | n/a |
| Duplicate actions from 125 concurrent re-executions | 0 | n/a |
| Stale-evidence executions blocked | 8 / 8 | n/a |
| Reproducibility (identical proof hash) | 100% | — |

**Read these honestly.** One team wrote both the cases and the engine, so 25/25 shows the engine implements its stated policy. It is not evidence of generalization. The baseline is a deliberately simple strawman that shows what evidence-blind automation gets wrong, not a competitor. The benchmark ran with the model in deterministic-fallback mode.

## Sponsor technology — truthful status

| Sponsor | Use in PayProof | Status in this repo |
|---|---|---|
| NVIDIA Nemotron | Explanation and strongest-counterargument phrasing (cite-checked) | **Implemented, tested against a local OpenAI-compatible stub only.** Not run against live Nemotron (no key in the build environment). |
| Meterless Nightshift | AI provider for Nemotron (`LLM_BASE_URL` → Nightshift endpoint) | **Not verified.** Nightshift has no Linux build and wasn't available here. |
| Meterless Engine | World Model ranking of counterfactual scenarios (advisory; cannot change amounts) | **Adapter only; HTTP contract is an assumption and is untested.** Deterministic ranking is the default. |
| Zetaris | Federated query over 6 source systems via allowlisted SQL templates | **Adapter only, untested against Zetaris.** Local fixtures are the default, with per-system provenance shown in the UI. |
| Cursor | Development environment | `.cursor/rules/payproof.mdc` included. This build session used Claude Code. |

Details and the remaining steps are in [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md). The organiser rules (as relayed in a public team tracker) require a Meterless engine in a real feature and Nightshift as the AI provider. **These are open submission blockers until they are verified on a machine running Meterless.**

## Repository map

```
payproof/
  money.py           exact Decimal helpers (floats rejected)
  sources.py         LocalFixtureSource, ZetarisSource (allowlisted SQL), late-event overlay
  evidence.py        evidence index + provenance, identity resolution, evidence graph
  policy.py          deterministic commission engine (PLAN-AE-2026), scenario views
  counterfactual.py  scenario generation + replay
  workflow.py        investigator, skeptic, policy verifier, planner, validator, proof bundle
  llm.py             bounded Nemotron client (OpenAI-compatible) + deterministic fallback
  meterless.py       Meterless engine adapter (advisory ranking) + fallback
  actions.py         state machine, authz, idempotency, simulated adapter, hash-chained audit
  server.py          stdlib HTTP API + static UI
  bench.py           benchmark + baseline + safety suite
web/                 Decision Room (vanilla JS, no build)
data/cases/          25 synthetic source snapshots (6 systems each); data/plans.json
bench/               ground_truth.json (hand-written), results/latest.json
docs/                ARCHITECTURE, INTEGRATIONS, BENCHMARK, DEMO_SCRIPT, deck.html
tests/               unittest suite
```

## API

All calls carry `X-Demo-User: ana|fin|ctl|ops|rep`. This is demo-only authentication with synthetic users, and it is not production auth.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/cases` | queue (sales reps only see their own) |
| GET | `/api/cases/{id}` | full investigation: proof bundle, graph, counterfactuals, skeptic, action |
| GET | `/api/cases/{id}/sources` | original source records, unmodified |
| POST | `/api/cases/{id}/actions` | propose (analyst) |
| POST | `/api/actions/{id}/decision` | `{"decision":"approve"\|"reject"}` (approver, within limits) |
| POST | `/api/actions/{id}/execute` | header `Idempotency-Key` (payroll ops / controller) |
| POST | `/api/cases/{id}/simulate/late-event` | inject a late-arriving credit note (stale-evidence demo) |
| POST | `/api/sim/fail-next` | make the next adapter call fail |
| GET | `/api/audit` · `/api/integrations` · `/api/benchmark` | |

## Known limitations

- Action and audit state is in-memory: a restart resets the demo. The audit is also mirrored to `var/audit.jsonl`.
- There is one commission plan. Accelerators, quotas and multi-period clawback rules are out of scope.
- Authentication is a demo user switcher. Real deployment needs SSO plus role mapping.
- Sponsor integrations are unverified, as listed above.
