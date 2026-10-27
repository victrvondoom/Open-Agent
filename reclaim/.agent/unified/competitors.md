# Competitor scan — Open Agent Hackathon 2026 (20 public repos)

Research artifact for the lead engineer, used as input to `docs/COMPETITIVE_GAP_ANALYSIS.md`.
Compiled 2026-10-27 from each repo's default branch (HEAD) via `gh api`: metadata, README, file tree, and 1–3 high-value files per repo. Nothing was cloned or executed.

**Ground rules applied**
- Numbers are quoted verbatim from the named file. **We reproduced none of them.**
- "Mechanisms" are paraphrased ideas. No code or assets were copied.
- **Licence:** "none" means the API reports no SPDX id *and* the tree has no root LICENSE file. Under default copyright, treat these as all rights reserved.
- **Availability:** all 20 repos were public and readable. None was missing or private.

**Sponsor evidence levels** (judged only from the files read)
- **L3 (live):** the client code exists *and* committed receipts, traces or live logs exist.
- **L2 (code):** client code or contract tests (HTTP doubles, recordings) exist, but no live run is evidenced in what we read.
- **L1 (claim):** README intent or SQL scripts only.
- **n/c:** the repo explicitly says it does not claim this sponsor.

---

## Landscape at a glance

| # | Repo | Track | Evaluation design | Independent or external labels? | Live sponsor evidence | Licence |
|---|---|---|---|---|---|---|
| 1 | osmancancet/whytrace | 02 | dev 7, seen held-out 8, **blind held-out 8 (×3 runs)**; rules-only and Nemotron-only baselines; Brier | **Yes** (blind set by a separate analyst) | L3 Zetaris, Nightshift, Nemotron | none |
| 2 | HarshitaAdlakha/causa | 02 | 4 live runs (3 planted stories + 1 control) | No | L3 | none (README says Apache-2.0) |
| 3 | esutedjo/MaintenanceAssistant (Cleris) | 02 | 200 engines vs NASA answer key; 357 seeded faults; gates vs Nemotron alone | **Yes** (NASA C-MAPSS key) | L3 (judges replay recorded runs) | Apache-2.0 |
| 4 | Jae3y/AuditWhy | 02 | tests and perturbation only | n/a (real SEC EDGAR data, no labels) | L3 (live preflight log) | none |
| 5 | Ramy888/black-box | 02 | 1 seeded incident; outcome assertions | No | L3 (demo replays a recorded live run) | Apache-2.0 |
| 6 | Aryamanironman/overturn | 02 | 1 synthetic case, 4 planted conflicts | No | L2/L3 (live artefacts committed) | none |
| 7 | Brunof94-debug/fechamento-claro-open-agent | 02 | 7 fictional orders; explicitly no accuracy claim | No | L3 Zetaris + Nightshift (Llama, not Nemotron) | MIT |
| 8 | TheRealNajim/haqi | 02 | 69 tests, no labelled set | n/a | Zetaris L2/L3, Nightshift L2, Nemotron direct | none |
| 9 | leitner-labs/proofline | 02 | 1 demo question | No | Zetaris L1, Nemotron L1, H-MEM in-process | none |
| 10 | Hemanth-Raja/shopfloor-os | 03 | 270 planted unsafe plans; 300 random plans scored by a runtime monitor; chaos ×15; Nemotron-only baseline | Partly (runtime-monitor label is independent of the critic) | L3 + 6,215 Ed25519 receipts | Apache-2.0 |
| 11 | rahulmahadik/sanctions-desk | 03 | 70-case exam + frozen held-out rounds; mutation 147/147; `npm run prove` | Partly (exam labels follow the rules' definitions) | L3 + 3,411 receipts | Apache-2.0 |
| 12 | Orielanalyst/PortalOne | 01 | tests and receipts only | n/a | L3 | none |
| 13 | mikey92/recallwhy | 01 | 322 recall/SKU pairs; model ladder; `check:claims` | **Yes** (barcodes printed in FDA/CPSC notices) | L3 | Apache-2.0 |
| 14 | JoeProAI/porch-light | 01 | national sweep counts; "no single score" | n/a | L3 | AGPL-3.0 |
| 15 | GestaltWorks/ConfigLeaf | 01 | **pre-registered** protocol, expert labels, held-out run once, C0–C4, Wilson CIs | **Yes** (operator labels, real items) | L3 + 375 verified receipts | MIT |
| 16 | Palmlore/Tiresias | 03 | 12 pre-committed companies + 3 controls, re-audited against EDGAR | **Yes** (external EDGAR re-check) | L3 | Apache-2.0 |
| 17 | Hasebul21/tradeflow | Wildcard | 25 cases incl. red team; every live run published | No | L3 Nightshift → Nemotron | MIT |
| 18 | EnriqueDGProg/PHIS-OpenAgent-2026 | not stated | seeded generator, dev vs held-out seeds; 12-dimension adversarial battery | Partly (frozen generator) | WM L3; Zetaris and NVIDIA owner-verified | none (scoped MIT notice) |
| 19 | daffa-athallah/pingo | 03 | 20 synthetic events | No | L3 (GPT-4o-mini handles perception) | Apache-2.0 |
| 20 | GitHubMoreLikeGitGud/clearshelf | 03 | 10 regression scenarios; evidence-quality metrics; extraction P/R | Partly (rule-derived reference labels) | L3 (Nemotron 4B on local Ollama) | Apache-2.0 |

---

## Track 02 direct competitors

### 1. osmancancet/whytrace — WhyTrace
- **Status, licence, pitch.** Pushed 2026-10-24. No root LICENSE (vendored Meterless directories carry Apache-2.0). Investigates account compromise for a university SOC across Entra ID, a mail gateway, a CMDB and CISA KEV. Verdicts: contain, monitor, benign or escalate.
- **Verification and "why".**
  - The pipeline runs Planner → Investigator ↔ Critic → DQ checks → Scout injection gate → Risk Gate → Reporter.
  - The Critic "reruns its OWN SQL" for every finding, for up to 3 rounds.
  - In the Risk Gate, code can veto the model.
  - `validateReport` requires every claim to cite a real `sql_id`.
  - `not_checked[]` lists what could not be verified.
- **Explainability** (`packages/agents/src/explain.ts`):
  - exact Shapley values over the deterministic policy;
  - leave-one-out verdicts and the smallest set of findings whose removal flips the verdict;
  - a deterministic "Why not <runner-up>?" sentence;
  - faithfulness@3: the narration must cite the top-3 attributed findings, otherwise one re-write is triggered.
- **Evaluation** (README.md, `evidence/heldout-b.md`, `evidence/calibration.md`):
  - **Sets:** dev 7 (self-authored and tuned), seen held-out 8, and blind held-out 8 "authored ... without seeing any WhyTrace code; labels were fixed before the run". Each case runs 3 times. The system is frozen at `2b28af2`, with an empty `git diff`.
  - **Blind set:** WhyTrace "15/24 (62.5%)", rules-only "**18/24 (75%)**", Nemotron alone "17/24 (71%)". False contains: 0, 6 and 2.
  - **Brier on the blind set:** "**0.2104** | 0.2256 | 0.2365".
  - **Dev set:** "**19/21 (90.5%)**".
- **Adversarial** (`evidence/adversarial.md`, `evidence/traps.md`):
  - "126/126 (100%) caught" planted near-miss claims across 6 categories: 105 by the Critic's re-query, 21 by the evidence validator.
  - 3 false-premise traps: "All three traps: A0 refused the premise."
  - Scout corpus: "injection precision 1.00, injection recall 1.00" on 10 examples.
  - The execution contract is HMAC-signed with a 5-minute TTL.
- **Sponsors.**
  - Zetaris USL over 4 sources, accessed only through "the 14 catalogue `SELECT`s" (L3).
  - Nightshift logs `receipt_id` and `routed_model` per call (L3, `evidence/model-routing.md`).
  - Nemotron 3.5 Super VL served every successful call; the Lightning lane "never returned a successful call".
  - Meterless engines pass "29/29" on the three deterministic engines.
  - The least-privilege Zetaris key is "documented, not yet enabled".
  - Cursor was the IDE.
- **UX.** A "Why this verdict" panel (attribution bars, "Would change the verdict" chips, a faithfulness badge) and a GitHub Pages replay.
- **Honesty.** The README admits rules-only is more accurate on both held-out sets and argues instead on error shape (zero false contains).

### 2. HarshitaAdlakha/causa — Causa
- **Status, licence, pitch.** Pushed 2026-10-25. The README says "Apache-2.0", but there is no root LICENSE file. It explains why revenue moved across a federated ERP and CRM. This is the numeric-variance framing closest to PayProof's.
- **Mechanisms.**
  - Pipeline: Planner (H-MEM recall, ≤5 ranked hypotheses) → Analyst (SQL) ⇄ Critic ("8 checks + Nemotron", ≤2 revisions) → Reporter.
  - The Reporter's figure guard rejects any number that is not in the approved claims or their queries; sums of 2–3 cited values are allowed.
  - Confidence "starts at 45%" and falls "by 25 points when no contract, tender or pricing event in the CRM explains the drivers".
- **Evaluation** (README.md):
  - 4 live runs on team-synthetic data with 3 planted stories plus 1 control. For the control, "the cause is reported as not established" at 70%.
  - "9 pipeline tests", including anti-hardcoding tests: totals must equal an independent SQL query, and the runtime never reads the example outputs.
  - No held-out set, no metrics, and no injection or adversarial tests found.
- **Sponsors.**
  - Zetaris REST with a federated CRM⋈ERP join (L3: `src/data/zetaris.ts`, 4 committed `output_examples/*.trace.jsonl`).
  - Nightshift is the only provider (L3: `src/llm.ts`).
  - Nemotron 3.5 Lightning and 3 Ultra, with the model recorded in every trace event.
  - H-MEM conformance "13/13".
- **UX.** A browser replay of the real runs. Every `[Qn]` citation opens its SQL and rows. Helpful/Wrong feedback adjusts H-MEM trust.

### 3. esutedjo/MaintenanceAssistant — Cleris
- **Status, licence, pitch.** Apache-2.0, pushed 2026-10-27. A turbofan MRO clearance brief "with every number checked by code".
- **Mechanisms.**
  - The planner routes each gap to the agent that can fix it.
  - Rule checks run with no LLM.
  - The critic combines code checks with Nemotron trying to "disprove the brief"; only challenges that code confirms send work back.
  - After round 3 the case closes as "insufficient evidence".
  - The engineer's sign-off is bound to the brief by a hash.
  - Case-memory trust moves +0.05, −0.03 or −0.20.
- **Evaluation** (`evaluation/report.md`):
  - 200 engines scored against the NASA C-MAPSS answer key, "which the agents never read".
  - "Of the 45 engines that fail within 15 days, **100%** were sent for removal, swap or repair and 0 told to keep flying."
  - RUL A "RMSE 12.13", with 80% interval coverage after conformal calibration.
- **Adversarial** (`evaluation/report.md`, README):
  - Seeded faulty briefs "**357 of 357 (100%)**", "Clean briefs flagged: 0". The README calls this "a self-test".
  - Input corruptions "116 of 116".
  - Gates vs Nemotron alone on 42 corrupted briefs: gates "42 of 42"; Nemotron "**3 of 41**", with "Challenges raised: 150; refuted by code: 147" (`evaluation/llm_critic_report.md`).
- **Sponsors.**
  - Zetaris REST SQL, SELECT-only (L3; README cites "39 Zetaris reads" across five committed live runs).
  - Nightshift is the only provider. The critic runs as its own Nightshift app pinned to Nemotron, and the trace notes "critic lane not pinned to Nemotron" when another model answers.
  - World Model 8/8 and H-MEM 13/13.
  - Cursor was used.
  - In judges' sample mode, Nemotron's part is recorded replies, labelled as such.
- **UX.** A judge's 5-minute path and a replay of six live runs. The regulatory map reports "26 requirements, 2 met, 15 partly met, 9 not met" (README).

### 4. Jae3y/AuditWhy
- **Status, licence, pitch.** No licence. Pushed 2026-10-27. Answers "why don't our numbers match?" using real SEC EDGAR filings (10 companies), the SIC taxonomy and 2 synthetic internal tables.
- **Mechanisms.**
  - Hypotheses H1–H4 start `pending` and declare which datasets they require.
  - A claim whose datasets return 0 rows or `TABLE_NOT_FOUND` becomes an `untested_factor`, together with the data needed to test it.
  - Statistical gate: `|r| ≥ 0.7` and `n ≥ 5`.
  - Confidence is the lower bound of the Fisher-z 95% CI, "discounted 5% per untested one".
  - The reviewer bans causal language about blocked factors.
  - The evaluator runs its own `SHOW DQ` to catch rows silently dropped by a join.
- **Evaluation.** No labelled set. "83 tests", perturbation tests that change the data and expect the verdict to change (`tests/test_investigation_integrity.py`), and CI.
- **Safety.** A Scout 5-layer guard blocks "DROP TABLE & exfiltration". `tests/test_security.py` covers write refusal, path traversal, key redirect, `.env` injection and PII redaction.
- **Sponsors.**
  - L3 preflight log `docs/live_check_2026-10-27.txt`: "[PASS] chat completion: meterless/auto -> 'ready' (served by nvidia/nemotron-3.5-bolt-e4b)", plus Zetaris table reads.
  - All 4 Meterless engines are in `app/engines/`.
  - Direct NVIDIA NIM serves as a fallback.
- **UX.** A lineage dashboard and a public Vercel demo (sample mode).

### 5. Ramy888/black-box — Black Box
- **Status, licence, pitch.** Apache-2.0, pushed 2026-10-24. A crash investigator for AI agents: it explains why a refund agent paid "40 refunds, 69,422 EGP, outside the live policy".
- **Mechanisms.**
  - Witnesses gather evidence with no model.
  - The Skeptic "re-runs every cited Zetaris query itself (a claim whose rows do not reproduce is struck with no model call)" and runs its own probes.
  - A Counterpart persona cross-examines; an uncited answer marks the claim "weak".
  - The Remediator compiles the root cause into a guardrail; a human HMAC-signs it, and the gate refuses anything "changed by a single character".
  - The **Airlock** replays the 40 bad requests through the real agent: "The guardrail pays 0." It runs in an always-rolled-back transaction.
  - The World Model answers point-in-time questions ("which policy was live at 10:00 on 21 Oct?").
- **Evaluation.** One seeded scenario (seed 417, 137 events). `npm run demo:check` asserts the outcome. 4 example inputs include user-submitted "challenge" hypotheses: one is struck, one survives.
- **Sponsors.**
  - Zetaris REST across Postgres, JSON and CSV (L3: `server/data/zetaris.ts`, `data/recordings/`).
  - Nightshift compute receipts (L3).
  - World Model and H-MEM.
  - Nemotron 3.5 Lightning.
  - The demo investigation is "replayed from a recorded live run"; the Airlock runs live. Cursor "was not used".
- **UX.** An SSE "Investigation Room" and a visible thinking-budget ladder (2,048 → 4,096 → 8,192 tokens).

### 6. Aryamanironman/overturn — OVERTURN
- **Status, licence, pitch.** No licence. Pushed 2026-10-27. It answers a health-insurance denial with evidence. **This is the closest domain overlap with RECLAIM** (insurance and healthcare disputes).
- **Mechanisms.**
  - The Reconciler is the only agent that calls `run_sql`.
  - The Critic runs `conflict_check` and `adversarial_review`.
  - A Nemotron "Advocate" argues the insurer's side.
  - Loops are bounded (4, then 3), followed by "one human question".
  - The appeal score is deterministic Python, capped when a required document is missing. The next-best action names the missing document and the projected score (84 → 100).
  - Missing documents are "never fabricated". The record is a hash chain.
- **Counterfactual provenance** (README.md). Removing a source shows the score delta, e.g. "policy clauses | 84 → 65 | −19" and "EOB | 84 → 84 | 0".
- **Evaluation.** One synthetic case (Ava) with 4 planted conflicts, and "37 tests pass", including Zetaris and Nightshift contract tests against local HTTP doubles. No benchmark.
- **Sponsors.**
  - Zetaris: 7 sources, a USL and 5 DQ rules (L2 code and tests).
  - The README claims live verification "27–28 October 2026", with "all 11 agent calls ... served by `nvidia/nemotron-3-ultra-550b-a55b`". Artefacts exist in `output_examples/live/`. **We did not reproduce this.**
  - Scout is explicitly not claimed.
- **UX.** `receipt.html` evidence map and an appeal packet in md and json. Films run in SAMPLE_MODE with stubs.

### 7. Brunof94-debug/fechamento-claro-open-agent — Fechamento Claro
- **Status, licence, pitch.** MIT (`LICENSE`; GitHub reports NOASSERTION). Submitted 23 Oct. Traces a settlement difference "to its source row" across order, settlement and refund sources. This overlaps PayProof's payment-dispute framing.
- **Mechanisms.**
  - An integer-cent reconciliation must equal the Zetaris totals, or the close is refused.
  - The model picks only from bounded, indexed actions: "Unknown choices are refused."
  - "Only inspected findings can reach the answer."
  - The local model file is SHA-256-verified (`evidence/model-integrity.json`).
- **Evaluation.** "Only seven fictional orders are demonstrated; no production accuracy or time-saving claim is made." "19 automated tests pass", with the caveat that stub tests "do not prove real Runtime execution".
- **Sponsors.**
  - Local Docker Zetaris via JDBC (L3: `evidence/zetaris-close.json`, `evidence/live-workflow.json`).
  - H-MEM in-memory.
  - Nightshift 1.2.1 serving **Llama 3.1 8B** (L3: `evidence/nightshift-*.json`).
  - "NVIDIA bonus | Not claimed" (n/c).
  - Cursor review documented in `docs/CURSOR-REVIEW.md`.

### 8. TheRealNajim/haqi
- **Status, licence, pitch.** No licence. The README says the demo video is "pending". Answers "can I play outside?" for an asthmatic child in Lagos, using OpenAQ, WAQI, OpenWeather, NASA FIRMS and a Zetaris view.
- **Mechanisms.**
  - There is "zero LLM in the verdict".
  - Readings are combined by unit group (µg/m³ is never blended with AQI).
  - Stale readings alone can never produce a green verdict.
  - Questions beyond the forecast horizon are refused.
  - Every verdict goes into an append-only ledger; `/why/{id}` renders it as a graph.
  - The narrator reads "only the ledger".
- **Standout.** A `/proof` self-audit route where "each claim names the test that enforces it", and a "Negative proofs (attempts to break it)" table.
- **Evaluation.** "69 tests". No labelled set.
- **Sponsors.**
  - Zetaris through a REST tunnel (L2/L3; reports `reachable:false` when down).
  - Nightshift narration "code shipped and tested; the slot reports `configured:false`" (L2, not live).
  - Nemotron `nemotron-3.5-bolt-e4b` via the NVIDIA hosted API, not via Nightshift.

### 9. leitner-labs/proofline — Proofline
- **Status, licence, pitch.** No licence. Small repo, pushed 2026-10-23. Answers a supplier-switch question for a fictional roaster, linking claims to rows.
- **Mechanisms.** Every executed query gets a lineage id that flows into the citations along with the retrieval time. "Unverifiable claims never ship." H-MEM's trust ledger audits each write.
- **Evaluation.** One demo question and one test file (`test/agent.test.ts`). No metrics.
- **Sponsors.**
  - Zetaris is a "pattern" only: the demo runs on local SQLite/CSV, and the `zetaris/*.sql` scripts were not executed (L1).
  - Nemotron is a "target model provider" (L1).
  - H-MEM is vendored, with conformance 13/13.

---

## High-engineering entries in other tracks

### 10. Hemanth-Raja/shopfloor-os (Track 3)
- **Status, licence, pitch.** Apache-2.0 plus DATA_LICENSE.md, pushed 2026-10-27. Incident response and AGV dispatch in a simulated car-assembly hall.
- **Mechanisms.**
  - Nemotron proposes; an OSHA critic with clause citations, a simulated dry run and a restraint gate decide.
  - World Model `ground()` rejects ids that do not exist.
  - Autonomy runs from level 0 to 3; "No level lets the agents send a person into a hazard without approval."
  - `/api/verify/<id>` re-derives a decision with no model.
  - The agents' own logs are federated into Zetaris so they can be queried with SQL.
- **Evaluation** (`docs/eval.md`):
  - 270 plans with a planted hazard, labelled by an "independent oracle": "Unsafe plans caught by the critic: **216/216 (100%)**"; "Safe plans wrongly rejected: 0/54 (0%)".
  - 300 random plans scored only by the runtime monitor: "**69/69 (100%)**" rejected.
  - The live Nemotron-only baseline produced "**6/27 (22%)**" unsafe or ungrounded plans; in the full loop, "unsafe plans executed: **0**".
  - Monitor Brier score "**0.0958** vs threshold alarm 0.3917".
  - Stability measured by Jaccard similarity across repeated runs.
- **Chaos** (`docs/chaos.md`). "**15 of 15 scenarios keep their property. Unsafe plans executed: 0.**" Scenarios include 60% 429/5xx errors, broken JSON, "Nightshift serves a different model than requested", and a runaway call budget.
- **Sponsors.**
  - Zetaris: 4 sources, a USL, and a read-only agent role so that writes are refused by Zetaris itself (L3).
  - World Model, H-MEM and Markovian ported to Python: "39 passed".
  - Three Nemotron models, each on its own Nightshift app: "6,215 of 6,215 Ed25519 receipts verify" (L3).
  - A Cursor rules file.

### 11. rahulmahadik/sanctions-desk (Track 3)
- **Status, licence, pitch.** Apache-2.0, pushed 2026-10-26. Fail-closed triage of sanctions-screening alerts: "A person with the right entitlement approves it."
- **Mechanisms.**
  - A second step "re-reads every fact the recommendation cites".
  - A policy guard stopped a close because "Tehran" appeared in a payment reference.
  - Roles: analyst, approver, viewer and policy_admin.
  - A less-cautious override needs an approver; a close needs a second, different approver; a block needs two people.
  - Every review produces a sealed, hashed record.
- **Evaluation** (README results box):
  - **70-case exam, wrongly closed:** "full system 0 of 43 (0–8%); Nemotron alone 3 of 43 (2–19%) ... 6 of 43 (7–27%)".
  - **Clear cases closed:** "Clear cases closed: full system 12 of 25 (30–67%) ... deterministic rules 25 of 25 (87–100%)".
  - **Trivial baseline:** "Escalate everything: 0 of 43 wrongly closed and 0 of 25 clears".
  - **Blind held-out rounds:** "4 of 48 against 13 of 48 for the deterministic rules".
  - Stated caveats: one run each, and exam labels "follow the same definitions as the rules".
- **Proof script** (`eval/PROVE.md`). "PASS: 7 of 7 checks passed", including:
  - critic mutation "147 of 147 changed facts caught", with no false alarms on 25/25 unchanged decisions;
  - "Preregistration: ... file hash matches" against freeze commits;
  - a secrets scan;
  - "3,411 signed receipts ... all verified against the pinned key".
- **Sponsors.** Zetaris L3. Signed Nightshift receipts L3. Nemotron Ultra and Lightning, with an Ollama backup that is labelled. Adding a new source changed "0 lines" of agent code (`compare/new-source/RESULT.txt`).

### 12. Orielanalyst/PortalOne — ReliefIntel (Track 1)
- **Status, licence, pitch.** No root licence (a data subfolder is CC BY 4.0). Pushed 2026-10-27. Humanitarian mission intelligence that produces a cited committee report and a GIS pack.
- **Mechanisms.**
  - Plan v1 is published *before* the Evaluator critiques it; later versions show text diffs.
  - World Model **evidence-dependent invalidation**: changed evidence withdraws a proposal and commissions a replacement.
  - A "Token Firewall pattern": the structured question is resolved in Zetaris before spending model context.
  - Routes follow the road graph; "the language model does not invent a line".
- **Evaluation.** "187 tests in 25 files ... passed locally"; "no hosted green result is claimed" because of a CI billing lock. No accuracy benchmark.
- **Sponsors.** Zetaris USL receipt (L3: `docs/evidence/zetaris-usl-2026-10-27.json`). Nightshift streaming with model receipts (L3). World Model passes 8 conformance checks.

### 13. mikey92/recallwhy — RecallWhy (Track 1)
- **Status, licence, pitch.** Apache-2.0, pushed 2026-10-26. Finds which recalled products are on a retailer's shelves and why, joining live CPSC/openFDA feeds with an ERP and a supplier portal.
- **Mechanisms.**
  - The Auditor re-derives every number "with its own SQL" and rejects a dismissal whose own quote names our item.
  - A pull list is withheld unless it equals the Auditor's on-hand number.
  - The Cartographer proves a supplier's barcode rule on all of that supplier's rows, then writes the repaired join back into Zetaris with lineage and a DQ rule.
- **Evaluation** (`eval/EVAL.md`):
  - 322 recall/SKU pairs. Labels come from barcodes printed in the notices; `ground_truth.csv` is "never read by the agents".
  - Ultra full system: "**134** | **1** | **1** | 30" (caught, wrongly dismissed, false alarms, sent to a person). Rules only: "89 | 0 | 0 | 233".
  - Missed recalls (README): "5 by the same model alone, 4 by the agents without the Auditor, 1 by the full system".
  - Real-product test with barcodes hidden: "55/97 caught ... 2/152 false alarms".
- **Claims discipline.** `CLAIMS.md` plus `npm run check:claims` recomputes the headline numbers in README, EVAL, the deck and the site. `check:repro` re-runs the model-free evaluations.
- **Sponsors.**
  - Live Zetaris: REST and JDBC sources, write-back views, a 7-table USL and 18 DQ rules (L3).
  - Meterless engines "byte-identical to upstream"; Scout guard "10/10 on Scout's adversarial set".
  - Nightshift receipts, Nemotron Ultra and Lightning, and Cursor commits marked as such.

### 14. JoeProAI/porch-light — Porch Light (Track 1)
- **Status, licence, pitch.** AGPL-3.0, pushed 2026-10-27. When a storm warning drops, produces a ranked call sheet of care facilities per US county.
- **Mechanisms.** The ranking formula is published and refusals are shown: "Nemotron writes the draft. The formula sets the order." Scout signs the call-script path.
- **Evaluation** (`docs/eval.mdx`):
  - "There is no `eval/` harness and no single score."
  - Sweep: "Counties attempted | 3,235"; "Ranked counties | 2,490".
  - Drafts: "14,960 passed ... 480 failed and stayed failed" (README).
- **Standout.** Explicit README sections "What you can say" and "What this submission does not say".
- **Sponsors.** Zetaris JDBC (L3). Nightshift `meterless/deep` (L3). H-MEM, World Model and Markovian are "not claimed".

### 15. GestaltWorks/ConfigLeaf (Track 1)
- **Status, licence, pitch.** MIT, pushed 2026-10-27. A configuration-assurance agent for MSPs (DNS vs nginx vs backups).
- **Mechanisms.**
  - A falsifier judge writes "one SELECT that returns rows only when it is false".
  - A verdict "counts only when its signed receipt verifies, names the tier requested".
  - An Actor applies ROLLBACK or FIX on a real host and verifies each write with a probe.
- **Protocol** (`eval/PROTOCOL.md`), pre-registered:
  - Labels were written by the operator ("17 years of MSP operations") "without seeing any model output".
  - The split seed is sha256(labels.json).
  - The held-out set is run once and "published whatever they say".
  - Configurations C0 (SQL only) to C4 (Ultra alone), 3 runs each.
  - A model substitution invalidates the run.
  - Results use Wilson 95% intervals and include planted false claims.
- **Held-out results** (README.md; `eval/results/2026-10-26T08-21-54Z/summary.md`):
  - "The SQL checks agree on 20 of 20 with no false alarm."
  - "Ultra alone agrees on 11 to 13 of 20 and raises a false alarm on 7 to 9."
  - "With Ultra as the falsifier the system raises none and strikes 8, 9 and 9 of 10 deliberately false claims."
  - "375 signatures verified, 0 mismatches."
- **Sponsors.** Zetaris, World Model, H-MEM, Nightshift Ed25519 receipts verified offline (L3), Nemotron Lightning and Ultra. Items are real deviations from the operator's estates, pseudonymised.

### 16. Palmlore/Tiresias (Track 3)
- **Status, licence, pitch.** Apache-2.0, pushed 2026-10-27. An evidence-backed "5 Whys" for why a reported figure changed between SEC filings.
- **Mechanisms** (`docs/causal-criteria.md`):
  - An intervention test reports the "share explained" and the residual.
  - Links are labelled breakdown, causal, leverage or background; "an accounting identity or a breakdown of the total is not a cause".
  - Every run ends in a named state: actionable, branched, evidence-frontier, external-driver or budget.
  - A new Zetaris source can be registered mid-run behind a human gate.
  - H-MEM stores "lessons, not answers"; the critic can reject a recalled lesson, and memory can be purged.
- **Evaluation** (README.md; `docs/measurements/coverage-sweep-2026-10-26.md`):
  - 12 spin-off companies "we did not pick", plus 3 controls, were committed before running and re-checked against EDGAR outside the system.
  - "No wrong number. 6 companies got an answer ... The audit found all 6 correct, 4 with caveats ... none wrong."
  - "5 runs stopped at the evidence frontier."
  - "Median 13.5 s per question."
- **Sponsors.** Live Zetaris registration (L3: `docs/measurements/zetaris-usl-2026-10-27.jsonl`), Nightshift with Nemotron, and the official H-MEM engine.
- **UX.** "Pause at each decision (5 s to take over)."

### 17. Hasebul21/tradeflow (Wildcard)
- **Status, licence, pitch.** MIT, pushed 2026-10-24. Review agents for a Dhaka Stock Exchange portfolio on synthetic data: "never trading advice".
- **Mechanisms.** The evaluator code check "rejects a finding whose number is not in the rows it cites". Prompt hashes, the routed model, cost and commit are recorded for every eval run.
- **Evaluation** (`evals/RESULTS.md`). Sample mode: "25 passed, 0 failed". **Every live run is published**, from "run 1 ... 7 passed, 13 failed" up to run 7 (commit `cef9544`) "20 passed, 5 failed".
- **Red team** (`evals/redteam/cases.json`). Advice requests, injected note/announcement/tool-call, out-of-range dates and off-topic questions, each with `must_not_mention` assertions.
- **Sponsors.** Nightshift → `openrouter/nvidia/nemotron-3.5-lightning` (L3). Zetaris with a local-rows fallback.

### 18. EnriqueDGProg/PHIS-OpenAgent-2026 (track not stated)
- **Status, licence, pitch.** No root licence (scoped MIT notice). Pushed 2026-10-27. Evidence-first personal health investigation over a fictional dataset of 1,080 records across 180 days.
- **Mechanisms.** Deterministic tools compute the results; a model abstention "does not erase scientifically valid PHIS results". Clinical questions get an abstention, and no causal claims are made.
- **Evaluation** (`docs/SYNTHETIC_BENCHMARK_METHODOLOGY_2026-10-23.md`).
  - The generator is frozen, with predeclared lagged effects, a negative-control variable and a confounded case.
  - Dev seeds 3101/3102 vs untouched held-out seeds 4101/4102.
  - The protocol was committed before any results.
- **Adversarial** (`docs/EVALUATION_ADVERSARIAL_GATE_2026-10-22.md`). 12 dimensions, all PASS, including "0.000000 drift, identical SHA256" across 5 runs. The same document **self-scores "91 / 100"**, with sponsors at "1 / 10 PARTIAL" on that date.
- **Sponsors.** World Model receipt (L3: `submission/FINAL_COMBINED_RECEIPT.md`). Zetaris verified "on the owner's preconfigured local stack". NVIDIA through the direct API. Cursor "no usage claimed".

### 19. daffa-athallah/pingo — Pingo/Recall (Track 3)
- **Status, licence, pitch.** Apache-2.0, pushed 2026-10-27. Turns saved screenshots into grounded reminders.
- **Mechanisms.** The Critic holds "interruption authority": surface, stay silent, ask, request revision or verify context. Replayed examples are labelled `provenance: recorded`.
- **Evaluation** (README.md, `docs/impact.md`). "Measured on 20 synthetic events with real models: 9/10 relevant moments surfaced, 0/10 unrelated interruptions." "380 tests".
- **Sponsors.** Zetaris JDBC, H-MEM, Nightshift and Nemotron 3 Ultra. Perception uses GPT-4o-mini.

### 20. GitHubMoreLikeGitGud/clearshelf — ClearShelf (Track 3)
- **Status, licence, pitch.** Apache-2.0, pushed 2026-10-25. Allergen clearance and recall watch for online grocers: "every decision cited, every release signed".
- **Mechanisms.**
  - **Asymmetric autonomy:** HOLD and BLOCK apply automatically; CLEAR and RELEASE run only under an "officer-approved, HMAC-signed, single-use execution contract".
  - A post-write Zetaris DQ rule, `signed_clear`, flags any clearance row without a contract.
  - Contradictions are typed (source/source, model/verifier, memory/source, rule/rule): "None is settled by whichever write came last."
  - Statements still marked "(to confirm)" cannot be signed.
- **Evaluation** (README.md, `docs/eval-report.md`):
  - "Scenarios: 10 of 10 pass", described as "a regression check, not an accuracy score".
  - E-replay: "Re-running the cited SQL returns every cited row (95/95)".
  - Extraction: Nemotron precision "1.00", recall 0.78. The README admits "The planner adds no measured decision value" and "The lexicon alone outscored the model".
- **Adversarial.** The E8 injection fixture ends in HOLD, with the text "wrapped as untrusted". E10, a RELEASE without a contract, returns 403 and the ledger's sha256 is unchanged.
- **Sponsors.** Zetaris L3. Meterless engines blob-identical to upstream. Nemotron 3 Nano 4B on local Ollama. Cursor task files in `docs/cursor-tasks/`.

---

## Top patterns worth adopting (ranked for Track 02 judging)

**Judging weights**, as quoted in Causa's README (not verified against the official rules): Impact 30 · Technical 20 · Innovation 15 · Demo 15 · Product & UX 10 · Sponsor tech 10.

**Baseline for our side.**
- **PayProof:** 30 same-author synthetic cases and a rules baseline; 185 unauthorized attempts; ablations, P/R/F1 and latency; contradiction F1 on 15 hand-labelled records. `payproof/counterfactual.py` generates and replays *input what-if scenarios*. Zetaris and Nemotron are **not configured** on this machine.
- **Read-only grep of PayProof** found no held-out set, calibration, attribution, Wilson intervals, chaos suite or claims check.

| # | Pattern | Seen in | Why it matters for Track 02 | Do we have it? | Implementation idea (our stack) |
|---|---|---|---|---|---|
| 1 | **Independent held-out set, pre-registered and hash-frozen**, with external ground truth where possible | WhyTrace, ConfigLeaf, sanctions-desk, Tiresias, PHIS, Cleris, recallwhy | Credibility of our own headline (Technical); "verify every claim" applies to our benchmark too | **No** (BENCHMARK.md says "not an independent test set") | Add `bench/heldout/` written by someone who has not read `payproof/policy.py`, or produced by a frozen seeded generator. Commit `bench/PREREG.md` with sha256 and freeze commit. Bench refuses to run on a hash mismatch, reports dev and held-out separately, and publishes as-is. |
| 2 | **Baseline ladder** (trivial escalate-all, rules, LLM-alone, full) with error-shape metrics and 95% intervals | sanctions-desk, WhyTrace, ConfigLeaf, recallwhy, Cleris, shopfloor | Shows *why* each component exists; error shape (false pay vs false deny) beats raw accuracy | **Partial** (rules baseline and ablations; no escalate-all, no LLM-only, no CIs) | Add `escalate_all` and `llm_only` systems to `payproof/evaluation.py::run_system` (`llm_only` marked "not configured" without credentials). Report wrongly-paid, wrongly-denied and sent-to-human counts with Wilson 95% intervals. |
| 3 | **Planted-claim / mutation test of the verifier**, by category, with clean controls | WhyTrace (126), Cleris (357), sanctions-desk (147), shopfloor (270), ConfigLeaf | Directly measures "verify every material claim" | **Partial** (robustness eval perturbs whole evidence feeds; no per-claim catalogue) | `payproof/bench_mutation.py`: mutate one cited fact per category (amount ±1 cent or ±10%, effective date, rep ID, plan clause, invented record ID, uncited causal sentence). Count which stage catches it (skeptic, validator, missed); unmutated controls count false alarms. |
| 4 | **Independent re-derivation**: skeptic re-runs cited queries by a different path; falsifier emits an executable refutation; E-replay metric | WhyTrace, Black Box, recallwhy, ConfigLeaf, ClearShelf, Fechamento Claro | Turns "the skeptic agreed" into something a judge can re-run | **Partial** (skeptic/verifier stage exists; Zetaris not live) | Store each claim's `(source, template_id, params, row_ids_hash)`. The skeptic recomputes by an alternate path (e.g. aggregate in SQL vs in Python) and must match. Publish "cited evidence re-run: n/n reproduced". |
| 5 | **Deterministic attribution and a contrastive "why not"**, plus a narration-faithfulness check | WhyTrace (Shapley, flip set, faithfulness@3), OVERTURN (leave-one-source-out), Causa, AuditWhy | Track 02 is literally "explain WHY"; model-free attribution is checkable and demos well | **Partial** (input what-if counterfactuals only) | Our policy engine is deterministic, so compute leave-one-out and exact Shapley over evidence records (n ≤ 12) per decision. Render "Removing <record> flips PAY → HOLD" and "Why not DENY: …". If the Nemotron narration misses the top-3 attributed records, fall back to the deterministic narrator. |
| 6 | **False-premise traps, user "challenge" hypotheses, typed contradictions** | WhyTrace (traps), Black Box (challenge input), Causa (control), sanctions-desk, ClearShelf (typed contradictions) | "Find contradictions"; the strongest demo beat is the agent refusing the complainant's framing | **Partial** (5 adversarial/benign controls; record-level contradiction F1) | Add 3–5 trap disputes that confidently assert an underpayment the records refute, and the reverse. Add a "Challenge" box/API that returns survive or struck with evidence. Tag each contradiction with its kind. |
| 7 | **Explicit unknowns, plus the next evidence and the decision it would change** | WhyTrace `not_checked[]`, AuditWhy `untested_factors`, Causa, Tiresias end states, OVERTURN, ClearShelf "(to confirm)" | Honest "why" includes what wasn't verified; calibrated uncertainty | **Partial** (stale-evidence gate; report contents unconfirmed) | Add `not_checked[]` and `next_evidence[]` to the PayProof report and RECLAIM case summaries. Compute each entry's effect by re-running the policy with the record assumed present or absent. Cap confidence when a required source is missing. |
| 8 | **Claims ledger enforced in CI**, plus a "what we do not claim" section | recallwhy (`check:claims`), sanctions-desk (`prove`), haqi (`/proof`), Porch Light, ClearShelf | Our "never fabricate" rule, made checkable; prevents stale deck numbers | **Partial** (BENCHMARK.md generated from `bench/results/latest.json`; README, deck and docs not checked) | `scripts/check_claims.py` reads a `CLAIMS.yaml` (claim → JSON path → command) and fails CI if README, docs or `deck.html` disagree. Add a `GET /api/proof` route and a README "Not claimed" section (Zetaris/Nemotron not configured, synthetic data, same-author cases). |
| 9 | **Signed model-call receipts with served-vs-requested model checks** | shopfloor, ConfigLeaf, sanctions-desk, WhyTrace, Cleris | Sponsor-tech score and NVIDIA "logs show the model" | **No** (no credentials on this machine) | When credentials exist, log `requested_model`, `routed_model` and `receipt_id` per call and flag mismatches in the UI. Until then keep "NOT configured" visible, never "LIVE". |
| 10 | **Chaos / fault-injection suite with must-hold properties** | shopfloor (15 scenarios), Cleris, AuditWhy, recallwhy, WhyTrace | Technical score; safety under provider failure | **Partial** (deterministic narrator fallback, feed-down robustness) | `tests/test_chaos.py` with a fake transport for `payproof/llm.py` and `payproof/sources.py` (timeout, 429 storm, broken JSON, empty reply, wrong model, Zetaris down mid-run). Assert: a decision or escalation is reached, 0 unauthorized actions, and the report shows a degraded flag and confidence penalty. |
| 11 | **Prove the fix: post-action verification and replay** | Black Box (Airlock), ClearShelf (post-write DQ, 403 with sha256 unchanged), ConfigLeaf (write probes), shopfloor | "Permit only authorized actions": show the gate holds *after* the fact | **Partial** (approval-gated sandbox, stale gate, idempotency, 185 attempts) | After each sandbox payout, run an independent reconciliation asserting the ledger delta equals the approved amount and no unapproved row exists. In the demo, replay the unauthorized corpus and show the ledger sha256 unchanged. |
| 12 | **Asymmetric autonomy and four-eyes on the risky direction** | ClearShelf, sanctions-desk, shopfloor (levels 0–3), Cleris | Maker-checker is the language adjudicators and regulators use | **Partial** (approval tokens; approval-gated actions) | In `payproof/actions.py`, let hold or request-evidence run unapproved. Require two distinct approvers above an amount threshold or for a DENY → PAY override, with both identities in the signed contract. |
| 13 | **Calibration and run-to-run stability** | WhyTrace (Brier, confidence on wrong answers), shopfloor, sanctions-desk, ConfigLeaf, PHIS | Shows that our confidence numbers mean something | **Partial** (`evaluate(repeats=5)` exists) | Report the Brier score of decision confidence, mean confidence on wrong decisions, and decision agreement across the 5 repeats. |
| 14 | **Evidence-dependent invalidation / "as of" view** | PortalOne, Black Box (point-in-time fold), ClearShelf ("what did we know when?") | Explains why an answer changed over time | **Largely yes** (stale-evidence gate, World Model provenance) | Add an "as of" selector (plan or contract version in force on the payout date). Auto-mark an approved recommendation "superseded" when a newer source version lands, linking the two. |
| 15 | **No-install review: hosted replay of recorded runs, labelled as recorded** | WhyTrace, Causa, Cleris, recallwhy, sanctions-desk, Black Box, pingo | Demo and UX scores; judges can review in 2 minutes | **Likely no** (local stdlib server on :8360; RECLAIM is local) | Export a static `web/replay/` bundle (trace JSONL and report JSON per bench case) for GitHub Pages, with a banner: "Recorded deterministic sample run, not live". |

**Also noted, already covered by us:**
- Memory hygiene: "lessons not answers", a critic that can reject recalled memory, and purge (Tiresias, AuditWhy, Cleris, WhyTrace). Our H-MEM verified-precedent memory covers this. Optionally add a "critic rejected recalled precedent" counter and a purge endpoint.
- Domain overlaps to watch:
  - **OVERTURN** (insurance denial) overlaps RECLAIM.
  - **Fechamento Claro, Causa and AuditWhy** (financial discrepancy) overlap PayProof.
  - **Black Box** (refund overpayment) overlaps PayProof.

---

## Claims we must not make

1. **No cross-repo accuracy comparisons.** PayProof's 30/30 is on a same-author dev set. WhyTrace's 62.5% is on a blind held-out set with 3 runs and live models. ConfigLeaf's 20/20 is on operator-labelled real items. Cleris and recallwhy use external answer keys. Domains, label authors, protocols and run counts all differ; none of these comparisons is apples-to-apples.
2. **No "only one with …" or "first to …" claims** for any of these: skeptic/critic loops (nearly every repo), counterfactuals (WhyTrace's Shapley and flip set, OVERTURN's leave-one-source-out), HMAC-signed execution contracts (WhyTrace, AuditWhy, Black Box, ClearShelf), approval gates (Black Box, ClearShelf, sanctions-desk, Cleris), H-MEM or World Model use (most repos), or Scout injection guards (WhyTrace, AuditWhy, recallwhy).
3. **No comparison of our "0/185 unauthorized" or "stale blocked 10/10"** with shopfloor's "0 unsafe executed", ClearShelf's "403 / sha256 unchanged", sanctions-desk's "0 of 43 wrongly closed", or WhyTrace's "126/126". Each team wrote its own attack set, so these are not comparable.
4. **No "LIVE" sponsor claims.** Per context.md, Zetaris and Nemotron are not configured on this machine. Competitors publish live receipts (shopfloor, sanctions-desk, ConfigLeaf, Cleris, recallwhy, AuditWhy), so a "live" claim from us would be both false and easily disproved.
5. **No competitor number cited as verified or reproduced.** We ran none of their code. Attribute every number as "as reported in `<repo>/<path>` at HEAD on 2026-10-27".
6. **No reuse of competitor self-assessments as scores**, e.g. PHIS's "91 / 100" jury matrix is self-graded. Do not repeat OVERTURN's live-verification claim as verified fact.
7. **No claim that our contradiction F1 1.000 or 30/30 shows superiority.** Both are same-author, small-n results; our own BENCHMARK.md says so. Do not describe them as "independent", "held-out" or "real-world".
8. **No claim that "agents beat rules" in general.** WhyTrace and sanctions-desk both report rules-only winning on some metrics. Our 30 vs 14 rules-only result holds only on our own set.
9. **No latency or cost comparisons.** Hardware, sample vs live mode, and hosted vs local models differ, e.g. ClearShelf runs Nemotron 4B locally on an RTX 4070 Ti SUPER, while Causa takes 7–16 minutes per live run on a laptop.
10. **No claims about competitors' gaps beyond what we read.** E.g. "Causa has no adversarial tests" means only that none were found in its README. Licence status means only that no root LICENSE was found.
11. **No borrowing of code, prompts, datasets, films or images.** 8 of the 20 repos have no root licence (all rights reserved by default), and OVERTURN's narration uses non-commercial voice weights. We take ideas only, with attribution.

---

## Unavailable repos

None. All 20 resolved via `gh api repos/OWNER/REPO` on 2026-10-27, with no 404s or private repos.
