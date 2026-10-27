# Demo script (≈3:30)

Setup: run `python3 -m payproof.server` and open http://127.0.0.1:8360. Click **Reset demo** and act as **Ana Lopez — analyst**.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Case queue | "Commission disputes are a finance-ops pain: five systems, five different answers. PayProof doesn't just explain the gap — it proves what *should* have been paid and only then lets anyone touch payroll." |
| 0:15 | CASE-1001 hero | "Maya says she's $3,000 short on a $60k deal. PayProof's verified answer is $1,100. It's VERIFIED, and the claim is partially supported." |
| 0:30 | 1 Evidence: timeline + graph | "These are raw records from HRIS, CRM, contracts, billing, comp and payroll. Note the timeline. PAY-44987 has a June value date but was recorded in July. Two clawbacks reference the same credit note. The CRM user 'M. Chen' links to Maya by email, not by name." Click PAY-44987 → drawer shows the unmodified record and its provenance. |
| 1:00 | 2 Hypothesis vs skeptic | "The investigator's waterfall runs from her $6,000 expectation through −$1,000 for the amendment and −$700 for uncollected cash to $4,300 due. Against $3,200 paid, she's owed $1,100. The skeptic then attacks that conclusion. Its strongest counterargument is that the late-recorded payment should be excluded, which would leave only $200. That was tested and ruled out under clause P-4.2. It also confirms the duplicate clawback." |
| 1:40 | 3 Calculation | "Every number here comes from deterministic Decimal code, with a rule and a citation. Excluded records are shown with their reasons. The verifier recomputes all of it independently." |
| 2:00 | 4 Counterfactuals | "These are hypothetical replays through the same engine. If timing used the recorded date, variance drops $900. If the duplicate never posted, $200. The amendment changes nothing here because collections cap the base. None of this is ever treated as a real event." |
| 2:20 | 6 Action | Click **Propose**. "That's a typed action with an idempotency key, the source fingerprint, preconditions and the required permission." Switch to **Maya Chen — sales_rep** and click **Approve**: a 403 conflict-of-interest refusal from the backend. Switch to **Farah — finance_approver** and Approve. Switch to **Oskar — payroll_ops** and **Execute**. |
| 2:50 | 7 Receipt | "It executes on the simulated payroll ledger, then independently re-investigates. Paid is now $4,300 and variance zero, so the postcondition passes. The hash-chained audit is valid. Clicking Execute again creates no duplicate." |
| 3:05 | CASE-1015 | "Here's the refusal case. The rep wants $4,500 now, but there's no contract in CLM. Status is NEEDS_EVIDENCE and the only action is a request for evidence. No money moves." |
| 3:20 | Header chips / docs | "We're explicit about integrations. In this recording Nemotron, Meterless and Zetaris run in fallback and say so. The benchmark has 25 hand-labelled cases: 25/25 versus 11/25 for a rules-only baseline, and zero unauthorized or duplicate actions across 151 and 125 attempts." |

Optional stale-evidence beat: after approval, click **⚡ Inject late credit note** and then **Execute**. The backend returns `STALE_EVIDENCE`, the action becomes EXPIRED and nothing is written. Re-investigation shows due $4,200.

> Before recording, replace the integration line with whatever the header chips actually show on your machine.
