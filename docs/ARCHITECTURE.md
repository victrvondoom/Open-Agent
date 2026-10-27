# Architecture

```
            ┌───────────── source adapters (sources.py) ─────────────┐
 HRIS  CRM  CLM  Billing  Comp  Payroll    LocalFixtureSource | ZetarisSource (allowlisted SQL)
            └──────────────┬──────────────────────────────────────────┘
                           │ original records (never mutated) + late-event overlay
                           ▼
                 EvidenceIndex (evidence.py) ── provenance, normalized facts, identity resolution
                           │
        ┌──────────────────┼────────────────────────────────────────────────┐
        ▼                  ▼                                                 │
  Policy engine (policy.py)  ◄── Scenario (hypothetical overlays)            │
  pure, Decimal, cited steps     counterfactual.py generates + replays        │
        │                                                                    │
        ▼                                                                    │
  Investigator → Skeptic → Policy verifier → Resolution planner → Final validator (workflow.py)
        │            │            │                  │                  │
        │            │   recompute + invariants      typed action       cite/amount checks
        │            │   conflict materiality        + idempotency key  allowlist, proof consistency
        │            └── falsification tests linked to counterfactuals
        ▼
  Proof bundle + run_id + proof_hash + source_fingerprint
        │
        ▼
  ActionService (actions.py): state machine · authz · limits · SoD · TTL · stale check
        │                                   │
        ▼                                   ▼
  SimulatedAdapter (idempotent)       AuditLog (hash chain) → receipt
        │
        └── postcondition: re-investigate with the simulated ledger → paid == due, variance 0
```

## Design decisions

- **Deterministic core, model at the edge.** Money, status, materiality, actions and authorization are all computed in code. The model (`llm.py`) receives the computed facts and returns sentences. The validator accepts a sentence only if every cited id exists and every dollar amount appears among the computed values. There are at most 2 calls per run, at temperature 0, with a timeout and a deterministic fallback.
- **Policy as clauses.** `data/plans.json` holds clause ids (P-2.1 … P-7.1) and those ids are cited in every calculation step, so a reviewer can trace each number back to a rule.
- **Temporal semantics.** Each record has `effective_at` and `recorded_at`. Policy P-4.2 says value dates govern timing. The skeptic always tests the recorded-date alternative where it matters, and counterfactual replay shows its effect.
- **Identity.** Only an email or HRIS-recorded alias counts as a strong signal. One strong match resolves the identity. Anything else is AMBIGUOUS/WEAK_ONLY, which blocks a VERIFIED result.
- **Materiality.** A conflict blocks the decision only if recomputing under each alternative changes the due amount.
- **Separation of data kinds.** Source records sit in `case.sources` and are immutable. Late events sit in an overlay. Derived facts are calculation steps. Hypotheses are investigator claims. Scenarios are `hypothetical: true` records that exist only inside a `Scenario` view. Simulated executions sit in `sim_ledger`.
- **Reproducibility.** `run_id = sha(source_fingerprint, engine_version, ledger)` and `proof_hash = sha(core outputs)`. The benchmark checks hash equality across runs.
- **Stale evidence.** Each action stores the source fingerprint from proposal. Approval and execution both recompute it, and any mismatch moves the action to `EXPIRED` with nothing written. Execution also re-checks that the paid total is unchanged.
- **At-most-once execution.** A process lock, a state check (EXECUTED/VERIFIED returns the existing receipt) and adapter-level idempotency-key dedupe guard it together. The benchmark fires 5 concurrent executions per action.
- **Minimal dependencies.** Python standard library only, with a vanilla JS UI and no build step, so judges can run it in one command.
- **Security.** No model-generated SQL or code is executed. The Zetaris adapter sends fixed templates with one bound parameter. Request bodies are size-limited, and the static file server prevents path traversal. Audit entries hold ids and amounts only, with no names or emails. Secrets come only from environment variables.
