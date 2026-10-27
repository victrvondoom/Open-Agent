# Demo script (recorded: 3:46, hard limit 4:00)

**Setup.** Run `python3 run.py` and open http://127.0.0.1:8360. Click **Reset demo** and act as **Ana Lopez — analyst**. Don't show API keys or `.env` on screen.

`docs/demo/payproof-demo.mp4` captures this exact flow from the real app. It is produced by `scripts/record_demo.js`, with caption bars added as narration. Every number, record id, status and live-check result in the captions is read from the live API or the rendered page at recording time. Voice-over is optional: the captions carry the script.

| Time | Screen | Say / show |
|---|---|---|
| 0:00 | CASE-1001 hero | "Commission disputes: five systems, five answers. PayProof proves what *should* have been paid before anyone touches payroll." |
| 0:10 | Hero | "Maya claims she is $3,000 short on a $60k deal. The verified variance is +$1,100: the claim is partially supported, and the proof is VERIFIED." |
| 0:19 | **Trace** | Show the eight recorded stages: intake → policy → counterfactual → federation → hypothesis → guard → adversarial → decision. Each has its own timing. There are no loops. A human approval gate follows. |
| 0:31 | 1 Evidence | "PAY-44987 has a June value date but was recorded in July. The CN-0077 clawback appears twice." Click PAY-44987 to open the unmodified record. |
| 0:48 | Provenance | "There are 18 entities and 20 bitemporal edges in the **Meterless World Model**. The verifier cross-checks against its as-of-cutoff view." |
| 0:59 | 2 Hypothesis vs skeptic | Walk the waterfall: $6,000 expected, −$1,000 amendment, −$700 uncollected, $4,300 due. Then the skeptic's strongest attack, the late-recorded payment: it is tested by replay and ruled out by P-4.2. |
| 1:20 | 3 Calculation · 4 Counterfactuals | "Every number comes from Decimal code, with a rule and a citation. The counterfactuals are hypothetical replays through the same engine." |
| 1:41 | 6 Action | Click **Propose**. The action carries its type, amount, permission, idempotency key, fingerprint and a **signed Scout contract**. As **Maya (rep)**, click Approve: a 403 conflict-of-interest refusal. **Farah (finance)** approves. **Oskar (payroll ops)** executes. |
| 2:15 | 7 Receipt | "It executes once on the simulated ledger and is re-investigated: variance 0, postcondition passed, hash chain valid." |
| 2:27 | **Precedents & security** on another case | "**Meterless H-MEM**: CASE-1001's verified outcome is now a precedent. This case shares a pattern and recalls it. Precedents inform the reviewer and never enter the calculation." Click **Compare**. |
| 2:48 | CASE-1026 | "**Meterless Scout**: the payroll memo carries an embedded instruction. It is quarantined, kept out of the model and flagged. The action escalates to controller approval." |
| 3:09 | CASE-1015 | "No contract in CLM, so the status is NEEDS_EVIDENCE. The only action is a request for evidence. No money moves." |
| 3:21 | **Integrations → Run live check** | "Real calls only. World Model, H-MEM and Scout pass. Zetaris and Nemotron are *not configured, not called*, and nothing is simulated in their place." |
| 3:34 | Benchmark caption | The benchmark has 30 hand-labelled synthetic cases. PayProof gets 30/30, against 14/30 for rules-only and 28/30 without the skeptic. There were 0 unauthorized and 0 duplicate actions. The cases were written alongside the engine. |

**Optional beats.**
- **Stale evidence:** after approval, click **⚡ Inject late credit note**, then **Execute**. The backend answers `STALE_EVIDENCE`, the action becomes EXPIRED, and nothing is written.
- **Escalate:** a finance approver can click **Escalate** to require controller approval.
- **Export dossier:** downloads the full decision record with its review-only disclaimer.

> If you record with Zetaris or Nemotron configured, the tiles and live check read LIVE only after a real call succeeds. Re-record so the captions match.
