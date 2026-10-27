"""PayProof programmatic entry point.

    python3 run.py                         start the Decision Room + API (PORT, HOST env; default 127.0.0.1:8360)
    python3 run.py --case CASE-1001        run one investigation, print a JSON result, write logs/
    python3 run.py --samples               regenerate samples/ (3 inputs with their outputs and traces)
    python3 run.py --check-integrations    make one real call to each configured sponsor service and report
                                           LIVE / CONFIGURED_UNVERIFIED / FALLBACK / UNAVAILABLE

SAMPLE_MODE=true forces local fixtures and the deterministic narrator (no network).
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from payproof import llm, sources  # noqa: E402
from payproof.integrations import integration_status  # noqa: E402
from payproof.world_model import write_audit_jsonl  # noqa: E402
from payproof.workflow import investigate  # noqa: E402

AGENTS = [
    {"name": "Investigator", "role": "assembles evidence and proposes the initial explanation and waterfall"},
    {"name": "Skeptic", "role": "searches for evidence that falsifies the explanation; replays counterfactuals"},
    {"name": "Policy verifier", "role": "recomputes every amount from cited records; checks invariants and conflict materiality"},
    {"name": "Resolution planner", "role": "proposes one typed, approval-gated action with an idempotency key"},
    {"name": "Final validator", "role": "rejects uncited claims, invented amounts and unsafe actions"},
]
SAMPLES = {"CASE-1001": "demo: partially supported underpayment",
           "CASE-1015": "negative: missing contract -> NEEDS_EVIDENCE",
           "CASE-1010": "contradiction: material amendment conflict -> DISPUTED"}


def run_case(case_id: str, run_label: str | None = None, logs_dir: Path = ROOT / "logs") -> dict:
    t0 = time.monotonic()
    src = sources.make_source()
    try:
        case = src.load_case(case_id)
    except KeyError:
        return {"run_id": run_label, "status": "error", "error": {"type": "UnknownCase", "message": case_id, "recoverable": False}}
    r = investigate(case, sources.load_plans())
    world = r.pop("_world")
    logs_dir.mkdir(parents=True, exist_ok=True)
    trace = logs_dir / f"{r['run_id']}-trace.jsonl"
    write_audit_jsonl(world, logs_dir / f"{r['run_id']}-world-model.jsonl")
    with trace.open("w") as fh:
        for step in r["calculation"]["steps"]:
            fh.write(json.dumps({"agent": "Policy verifier", "event": "calculation_step", **step}) + "\n")
        for f in r["skeptic"]["findings"]:
            fh.write(json.dumps({"agent": "Skeptic", "event": "finding", **f}) + "\n")
        for inv in r["verification"]["invariants"]:
            fh.write(json.dumps({"agent": "Policy verifier", "event": "invariant", **inv}) + "\n")
        fh.write(json.dumps({"agent": "Final validator", "event": "validation", **r["validation"]}, default=str) + "\n")
        fh.write(json.dumps({"agent": "Resolution planner", "event": "proposed_action", **r["proposed_action"]}) + "\n")
    c = dict(r["calculation"])
    if r["proof_status"] != "VERIFIED":  # an unverified amount is never reported as the answer
        c["due"] = c["delta"] = None
    return {
        "run_id": run_label or r["run_id"], "status": "success",
        "input": {"case_id": case_id, "claimed_shortfall": r["dispute"]["claimed_shortfall"], "narrative": r["dispute"]["narrative"]},
        "output": {
            "summary": f"{r['proof_status']} / {r['verdict']}: due {c['due']}, paid {c['paid']}, variance {c['delta']}",
            "proof_status": r["proof_status"], "verdict": r["verdict"], "due": c["due"], "paid": c["paid"], "variance": c["delta"],
            "blockers": c["blockers"], "skeptic_strongest": r["skeptic"]["strongest"],
            "recommendations": [r["proposed_action"]],
            "counterfactuals": [{k: x[k] for k in ("id", "title", "due", "delta", "delta_change")} for x in r["counterfactuals"][:5]],
            "artifacts": {"proof_hash": r["proof_hash"], "source_fingerprint": r["source_fingerprint"],
                          "world_model_state_hash": r["world_model_state_hash"], "provenance": r["sources_meta"]["provenance"]},
        },
        "agents": AGENTS, "trace_id": r["run_id"], "log_file": str(trace.relative_to(ROOT)) if trace.is_relative_to(ROOT) else str(trace),
        "model": r["telemetry"]["model_identity"], "model_calls": r["telemetry"]["model_calls"],
        "execution_time_seconds": round(time.monotonic() - t0, 3),
    }


def check_integrations() -> int:
    print("Checking sponsor integrations (one real call each where configured)...\n")
    out = run_case("CASE-1001", "integration-check")  # exercises World Model, Zetaris (if configured), Nemotron (if configured)
    if llm.config()["enabled"]:
        print("NVIDIA /models:", json.dumps(llm.verify_model(), indent=1))
    print("Sources:", json.dumps(out["output"]["artifacts"]["provenance"]))
    print("Model calls:", json.dumps(out["model_calls"]))
    print()
    for row in integration_status()["rows"]:
        print(f"  {row['state']:<22} {row['sponsor']:<16} {row['detail']}")
    return 0


def write_samples():
    d = ROOT / "samples"
    d.mkdir(exist_ok=True)
    index = []
    for cid, label in SAMPLES.items():
        out = run_case(cid, f"sample-{cid}", logs_dir=d / "logs")
        out.pop("execution_time_seconds")  # keep samples byte-stable across runs
        for m in out["model_calls"]:
            m.pop("latency_ms", None)
        (d / f"{cid}.input.json").write_text(json.dumps(out["input"], indent=2) + "\n")
        (d / f"{cid}.output.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
        index.append(f"- `{cid}` — {label}: {out['output']['summary']}")
    (d / "README.md").write_text("# Sample inputs and outputs\n\nGenerated by `python3 run.py --samples` "
                                 "(SAMPLE_MODE fixtures, deterministic). Traces in `samples/logs/`.\n\n" + "\n".join(index) + "\n")
    print("\n".join(index))


def main():
    args = sys.argv[1:]
    if not args:
        from payproof.server import main as serve
        return serve()
    if args[0] == "--case" and len(args) == 2:
        print(json.dumps(run_case(args[1]), indent=2, default=str))
        return 0
    if args == ["--samples"]:
        return write_samples()
    if args == ["--check-integrations"]:
        return check_integrations()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
