# Architecture

```
            ┌───────────── source adapters (sources.py) ─────────────┐
 HRIS  CRM  CLM  Billing  Comp  Payroll    LocalFixtureSource | ZetarisSource (documented REST SQL route)
            └──────────────┬──────────────────────────────────────────┘
                           │ original records (never mutated) + late-event overlay
                           ▼
 1 intake          EvidenceIndex (evidence.py): provenance, normalized facts, identity resolution;
                   malformed money fields → record excluded from a copy + MALFORMED_RECORD blocker
 2 policy          Policy engine (policy.py): pure, Decimal, cited steps, blockers, conflicts
 3 counterfactual  counterfactual.py: hypothetical Scenario overlays replayed through the same engine
 4 federation      Meterless World Model (world_model.py): provenance-stamped entities, bitemporal edges,
                   idempotent ingest, as-of-cutoff cross-check, ordered audit → logs/*.jsonl
 5 hypothesis      Investigator
 6 guard           Meterless Scout (scout.py): injection scan of every retrieved record → quarantine
 7 adversarial     Skeptic (falsification tests ↔ counterfactuals) → Policy verifier (recompute,
                   invariants, conflict materiality)
 8 decision        Resolution planner (typed action, idempotency key, escalation) → Final validator
                   (cites + amounts checked, allowlist, proof consistency)
                           │
                           ▼
  Proof bundle + trace + run_id + proof_hash + source_fingerprint
        │                                     └── H-MEM recall (hmem.py): precedents from *other* verified
        ▼                                         cases, shown to the reviewer; never an input
  ActionService (actions.py): Scout contract per step · state machine · authz · limits · SoD · TTL ·
                              stale check (fingerprint + World Model re-ingest) · human escalation
        │                                   │
        ▼                                   ▼
  SimulatedAdapter (idempotent)       AuditLog (hash chain) → receipt
        │
        └── postcondition: re-investigate with the simulated ledger → paid == due, variance 0
                 │
                 ▼
          H-MEM write: verified outcome → precedent (refs: case, action, receipt, proof hash)
```

## Pipeline trace

Every investigation records its eight stages in `trace`. Each entry has the stage key, the agent, the elapsed milliseconds and a one-line summary. The stages run once each, in a fixed order, with no loops. The Decision Room shows them as the **Agent pipeline trace**, followed by the **human approval gate** and **H-MEM learning**, which happens only after a human-approved action is verified. The trace ships in the exported dossier (`GET /api/cases/{id}/dossier`).

## Design decisions

- **Meterless World Model as canonical evidence state.** It powers four things: the evidence intake, the verifier's independent as-of-cutoff cross-check, the model's context builder, and the stale-evidence gate (an action snapshot is re-ingested; `changed=true` expires the action). See `docs/INTEGRATIONS.md`.
- **Meterless Scout Intent as the execution boundary.**
  - Propose, approve and execute each require a signed execution contract that is user-bound, capability-scoped and expires after 5 minutes. `ActionService` refuses without one, and the contracts are listed on the action.
  - Retrieved-record injections are quarantined: excluded from the model context, raised as an `SK-INJ` finding, and escalated to controller approval.
  - Intake injections are refused with a 422.
- **Meterless H-MEM as advisory memory.**
  - It writes only after `VERIFIED`, with a passed postcondition.
  - Recall excludes the case itself.
  - Precedents are never an input to the policy engine, the verifier or the planner.
  - Precedents persist in `var/hmem/` (state plus the trust ledger) and are cleared by a demo reset.

- **Deterministic core, model at the edge.** Money, status, materiality, actions and authorization are all computed in code. The model (`llm.py`) receives the computed facts and returns sentences. The validator accepts a sentence only if every cited id exists and every dollar amount appears among the computed values. There are at most 2 calls per run, at temperature 0, with a timeout and a deterministic fallback.
- **Policy as clauses.** `data/plans.json` holds clause ids (P-2.1 … P-7.1) and those ids are cited in every calculation step, so a reviewer can trace each number back to a rule.
- **Temporal semantics.** Each record has `effective_at` and `recorded_at`. Policy P-4.2 says value dates govern timing. The skeptic always tests the recorded-date alternative where it matters, and counterfactual replay shows its effect.
- **Identity.** Only an email or HRIS-recorded alias counts as a strong signal. One strong match resolves the identity. Anything else is AMBIGUOUS/WEAK_ONLY, which blocks a VERIFIED result.
- **Materiality.** A conflict blocks the decision only if recomputing under each alternative changes the due amount.
- **Malformed input.** Money fields must be exact decimals.
  - A record with a corrupted amount is excluded from a *copy* of the case; the original is never touched.
  - The record is reported as a `MALFORMED_RECORD` blocker, so the result is `NEEDS_EVIDENCE` and no money moves.
  - The robustness evaluation corrupts amounts, removes contracts or payroll, and takes the payments feed down across all 30 cases. Every run completed, and none produced an unverified payout.
- **Separation of data kinds.** Source records sit in `case.sources` and are immutable. Late events sit in an overlay. Derived facts are calculation steps. Hypotheses are investigator claims. Scenarios are `hypothetical: true` records that exist only inside a `Scenario` view. Simulated executions sit in `sim_ledger`.
- **Reproducibility.** `run_id = sha(source_fingerprint, engine_version, ledger)` and `proof_hash = sha(core outputs)`. The benchmark checks hash equality across runs.
- **Stale evidence.** Each action stores the source fingerprint from proposal. Approval and execution both recompute it, and any mismatch moves the action to `EXPIRED` with nothing written. Execution also re-checks that the paid total is unchanged.
- **Human control.** Approve, reject and escalate are human decisions. Escalate moves an action that is awaiting approval to controller approval. PayProof never issues a binding financial decision, and the dossier export carries a review-only disclaimer.
- **Operability.**
  - Every request gets a correlation id: a validated `X-Request-ID`, or a generated one. It is echoed in the response and written to structured JSON logs on stderr.
  - The UI cancels superseded case loads with an AbortController and ignores stale responses with a sequence guard.
  - It renders loading, empty, error (with retry) and degraded states.
- **At-most-once execution.** A process lock, a state check (EXECUTED/VERIFIED returns the existing receipt) and adapter-level idempotency-key dedupe guard it together. The benchmark fires 5 concurrent executions per action.
- **Minimal dependencies.** Python standard library only, with a vanilla JS UI and no build step, so judges can run it in one command.
- **Security.** No model-generated SQL or code is executed. The Zetaris adapter sends fixed templates whose only interpolated values (database identifier, case key) are regex-validated. Request bodies are size-limited, and the static file server prevents path traversal. Audit entries hold ids and amounts only, with no names or emails. Scout logs injection evidence as metadata only (`kind@offset`) and redacts PII and credentials. Secrets come only from environment variables. The contract signing key is `PAYPROOF_CONTRACT_SECRET`, or a random key per process.
