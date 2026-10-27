# Decisions — RECLAIM × PayProof Evidence Intelligence OS

## D1. Integration shape: HTTP bridge, not a code merge
PayProof (stdlib Python, port 8360) calls RECLAIM's FastAPI over HTTP (`payproof/reclaim_bridge.py`).
RECLAIM keeps owning intake, documents and its LangGraph agents; PayProof owns verification, the action gate and the UI.
Reason: both systems keep working independently; the contract is testable; no duplicated agent stack.

## D2. The prior-session scaffold is replaced where it was not genuine
Found in uncommitted WIP (backed up to scratchpad before any change):
- keyword-regex "citation verification" (any text with "RBI" + "section" => VERIFIED)
- `detect_dispute_contradictions` wrote `status="completed"` into records => fabricated contradictions
- `fetch_consumer_records` returned hardcoded records labelled `zetaris_*` with Zetaris unconfigured
- server: unauthenticated GET /api/reclaim/cases/{id}; silent fake cases and a fabricated agent run (fake citation)
  when RECLAIM was down; hardcoded queue amounts; every user mapped to RECLAIM `dev-user`; approve == instant receipt.
Public names stay where sensible; behaviour becomes genuine. Tests asserting the old heuristics are rewritten.

## D3. Consumer dispute vertical = airline cancellation refund (India), modelled like PayProof
Same proof-carrying pattern as the payroll engine: deterministic policy engine computes every amount/status;
counterfactual replay through the same engine; independent skeptic; invariant verifier; model narrates only.
Sources (federated through the Zetaris adapter when configured, else declared local fixtures):
`airline_pnr` (booking), `flight_ops` (cancellation event, alternate offers), `payments` (payment + refunds),
`airport_ops` (operational notices = evidence for/against "extraordinary circumstances").
RECLAIM contributes: the case (intake), documents, and agent outputs (research, citations, strategy, appeal draft).
Agent outputs are treated as CLAIMS TO VERIFY, never as evidence.

## D4. Citations are verified against a versioned local rulebook, never by keyword
`data/consumer/rulebook.json`: curated rule entries (instrument, clause, paraphrased text, parameters, as-of).
A citation is VERIFIED only if it resolves to a clause; numbers quoted in it must match the rule's parameters
(else MISQUOTED); unresolvable => UNVERIFIED (excluded from explanations). Rule texts are labelled paraphrase,
with "verify against the official text" — the system abstains rather than invent law.

## D5. Honesty labels on every measurement
Each metric/result carries `measured_with`: live | local-implementation | stub-server | synthetic-fixture | recorded.
No credentials exist for Zetaris/Nemotron on this machine => their paths are exercised through local stub servers
implementing the documented REST contracts, labelled `stub-server`, never `live`.

## D6. Ground truth is independent of the system under test
Benchmark cases are generated from seeded scenario parameters; the expected decision comes from the scenario
label table, not from running the engine. Holdout split uses a separate seed and is frozen with a manifest hash.

## D7. Tenancy
Users carry `tenant`; consumer cases carry `tenant_id`; every consumer endpoint enforces tenant + ownership.
Precedent memory writes are tenant-tagged and recall is tenant-filtered.
