# Demo script (target 3:30, hard limit 4:00)

**Setup.** Run `python3 run.py`, open http://127.0.0.1:8360, click **Reset demo** and act as **Ana Lopez — analyst**. Don't show API keys or `.env` on screen.

A recording-ready capture of this exact flow is at `docs/demo/payproof-demo.mp4`. It is produced from the real app by `scripts/record_demo.js`, with caption bars added as narration. Voice-over is optional: the captions carry the script.

| Time | Screen | Say / show |
|---|---|---|
| 0:00 | Case queue | "Sales-commission disputes: five systems, five answers. PayProof is for comp and payroll analysts. It proves what *should* have been paid before anyone touches payroll." |
| 0:15 | CASE-1001 hero | "Maya claims $3,000 short on a $60k deal. Verified answer: $1,100. The status is VERIFIED and the claim is partially supported." |
| 0:30 | 1 Evidence: timeline + graph | "Raw records from HRIS, CRM, contracts, billing, comp and payroll. PAY-44987 has a June value date but was recorded in July. The CN-0077 clawback appears twice. The CRM user 'M. Chen' links to Maya by email, not by name." Click PAY-44987 to open the unmodified record and its provenance. |
| 0:55 | Run provenance panel | "Every record is ingested into a **Meterless World Model** with provenance and bitemporal edges: when it happened versus when a system recorded it. The verifier cross-checks the engine against the World Model's as-of-cutoff view, and here they match." |
| 1:15 | 2 Hypothesis vs skeptic | "The waterfall runs from her $6,000 expectation through −$1,000 for the amendment and −$700 uncollected to $4,300 due, against $3,200 paid. The skeptic's strongest attack is to exclude the late-recorded payment, leaving only $200. It's tested by replay and ruled out by clause P-4.2. It also confirms the duplicate clawback." |
| 1:45 | 3 Calculation | "Every number comes from deterministic Decimal code, with a rule and a citation. Excluded records are shown with reasons. The model, when enabled, only phrases text, and the validator drops uncited claims and invented amounts." |
| 2:00 | 4 Counterfactuals | "These are hypothetical replays through the same engine. Recorded-date timing: −$900. No duplicate: −$200. The amendment changes nothing here because collections cap the base. Labelled hypothetical, never treated as events." |
| 2:20 | 6 Action | Click **Propose** and point at the type, amount, permission, idempotency key and fingerprint. Switch to **Maya — sales_rep** and **Approve**: a 403 conflict-of-interest refusal from the backend. Switch to **Farah — finance_approver** and Approve. Switch to **Oskar — payroll_ops** and **Execute**. |
| 2:55 | 7 Receipt | "It executes once on the simulated payroll ledger, then the case is independently re-investigated: paid $4,300, variance 0, postcondition passed. The hash chain is valid. Re-executing creates no duplicate." |
| 3:10 | CASE-1015 | "The refusal case: no contract in CLM. Status is NEEDS_EVIDENCE and the only action is a request for evidence. The hypothetical shows what the contract would establish, without assuming it." |
| 3:25 | Header chips | "Integration status is runtime truth. The Meterless World Model is live in-process. Zetaris and Nemotron show FALLBACK in this recording, and they say so. Benchmark: 25 hand-labelled cases, 25/25 versus 11/25 for a rules-only baseline. Zero unauthorized or duplicate actions." |

**Optional stale-evidence beat.** After approval, click **⚡ Inject late credit note**, then **Execute**. The backend answers `STALE_EVIDENCE: Meterless World Model ingest reported changed=True`, the action becomes EXPIRED, and nothing is written.

> If you record with Zetaris or Nemotron configured, the header chips will read LIVE only after a real call succeeds. Re-record the last beat to match what they show.
