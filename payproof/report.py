"""Generated documentation numbers. Nothing in the deck or README benchmark section is typed
by hand: `write_generated_docs(report)` (called by every benchmark run) recomputes the demo
case and rewrites the marked blocks from real output.

    docs/deck.html   <script id="deck-data" type="application/json"> … </script>
    README.md        <!-- BENCH:START --> … <!-- BENCH:END -->
"""

import json
import re
from pathlib import Path

from .sources import LocalFixtureSource, load_plans
from .workflow import investigate

ROOT = Path(__file__).resolve().parent.parent
DEMO_CASE = "CASE-1001"


def demo_snapshot(case_id: str = DEMO_CASE) -> dict:
    r = investigate(LocalFixtureSource(user_dir=None).load_case(case_id), load_plans())
    c = r["calculation"]
    strongest = next((f for f in r["skeptic"]["findings"] if f["id"] == r["skeptic"]["strongest"]), None)
    return {
        "case_id": case_id, "title": r["title"], "claimed": r["dispute"]["claimed_shortfall"],
        "due": c["due"], "paid": c["paid"], "delta": c["delta"], "proof_status": r["proof_status"], "verdict": r["verdict"],
        "waterfall": r["hypothesis"]["waterfall"],
        "counterfactuals": [{k: x[k] for k in ("title", "due", "delta_change")} for x in r["counterfactuals"][:5]],
        "strongest": {k: strongest[k] for k in ("title", "detail", "impact", "rule")} if strongest else None,
        "action": {k: r["proposed_action"][k] for k in ("type", "amount", "required_permission")},
    }


def test_count() -> int | None:
    import unittest
    try:
        return unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests")).countTestCases()
    except Exception:  # counting tests must never break doc generation
        return None


def deck_data(report: dict) -> dict:
    plans = load_plans()
    return {"generated_at": report["generated_at"], "sample_size": report["sample_size"],
            "agent": report["agent"], "baseline": report["baseline"], "safety": report["safety"],
            "approval_limits": plans["approval_limits"], "demo": demo_snapshot(), "tests": test_count()}


def _money(v):
    return "—" if v is None else f"{'-' if str(v).startswith('-') else ''}${abs(float(v)):,.2f}"


def readme_table(r: dict) -> str:
    a, b, s = r["agent"], r["baseline"], r["safety"]
    pct = lambda x: f"{x * 100:.0f}%"  # noqa: E731
    rows = [
        ("Decision accuracy (status + verdict + action, + amount when money moves)", f"{a['decisions_correct']}/{a['cases']}", f"{b['decisions_correct']}/{b['cases']}"),
        ("Exact due amount / mean abs. error", f"{a['money_exact']}/{a['money_cases']} / ${a['money_mean_abs_error']}", f"{b['money_exact']}/{b['money_cases']} / ${b['money_mean_abs_error']}"),
        ("Wrong payroll adjustments recommended", a["adjustment_false_positives"], b["adjustment_false_positives"]),
        ("Correct abstention (missing or contradictory evidence)", f"{a['correct_abstentions']}/{a['abstention_needed']}", f"{b['correct_abstentions']}/{b['abstention_needed']}"),
        ("Citation coverage of material claims", pct(a["citation_coverage"]), pct(b["citation_coverage"])),
        ("Unauthorized approvals/executions that succeeded", f"{s['unauthorized_actions_succeeded']} / {s['unauthorized_attempts']} attempts", "n/a"),
        (f"Duplicate actions from {s['duplicate_execution_requests']} concurrent re-executions", s["duplicate_actions_created"], "n/a"),
        ("Stale evidence between approval and execution: blocked", f"{s['stale_executions_blocked']} / {s['stale_evidence_scenarios']}", "n/a"),
        ("Forced postcondition failures: receipts issued anyway", f"{s['receipts_issued_despite_failed_postcondition']} / {s['forced_postcondition_failures']}", "n/a"),
        ("Reproducibility (identical proof hash)", pct(a["reproducibility"]), "n/a"),
        ("Latency per investigation (local)", f"p50 {a['latency_ms_p50']} ms", "n/a"),
    ]
    out = [f"_Generated from `bench/results/latest.json` ({r['generated_at']}, {r['sample_size']} cases, model calls: "
           f"`{json.dumps(a['model_calls_by_model'])}`)._", "", "| Metric | PayProof | Rules-only baseline |", "|---|---|---|"]
    out += [f"| {m} | {x} | {y} |" for m, x, y in rows]
    return "\n".join(out)


def readme_demo(m: dict) -> str:
    out = [f"_Generated from a live investigation of `{m['case_id']}` ({m['title']})._", "",
           f"Claimed shortfall **{_money(m['claimed'])}** → proof **{m['proof_status']}**, verdict **{m['verdict'].replace('_', ' ').lower()}**.", "",
           "| Reconciliation step | Amount | Evidence |", "|---|---|---|"]
    for r in m["waterfall"] or []:
        amt = _money(r["amount"]) if r["kind"] != "step" else (("+" if not str(r["amount"]).startswith("-") else "") + _money(r["amount"]))
        label = f"**{r['label']}**" if r["kind"] != "step" else r["label"]
        out.append(f"| {label} | {amt} | {', '.join(r['cites'])} |")
    st = m["strongest"]
    if st:
        out += ["", f"- **Skeptic's strongest counterargument:** {st['title']}. If true, the variance changes by "
                    f"{_money(st['impact'])}. {st['detail']}"]
    act = m["action"]
    out.append(f"- **Proposed action:** `{act['type']}`" + (f" {_money(act['amount'])}" if act["amount"] else "") +
               f", which needs `{act['required_permission']}`. The rep's own approval attempt gets a **403**. Once approved, payroll "
               "ops executes once on the simulated ledger. The case is then re-investigated and a hash-chained receipt is issued.")
    out.append("- **Counterfactuals (hypothetical):** " + "; ".join(
        f"{c['title']} → variance {('+' if c['delta_change'] and not str(c['delta_change']).startswith('-') else '')}{_money(c['delta_change'])}"
        for c in m["counterfactuals"][:3]))
    return "\n".join(out)


def _replace_block(text: str, start: str, end: str, body: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise ValueError(f"marker {start!r} not found")
    return pattern.sub(lambda _: f"{start}\n{body}\n{end}", text)


def write_generated_docs(report: dict, root: Path = ROOT):
    deck = root / "docs" / "deck.html"
    data = json.dumps(deck_data(report), separators=(",", ":"), default=str).replace("</", "<\\/")
    deck.write_text(_replace_block(deck.read_text(encoding="utf-8"), '<script id="deck-data" type="application/json">', "</script>", data), encoding="utf-8")
    readme = root / "README.md"
    text = _replace_block(readme.read_text(encoding="utf-8"), "<!-- BENCH:START -->", "<!-- BENCH:END -->", readme_table(report))
    readme.write_text(_replace_block(text, "<!-- DEMO:START -->", "<!-- DEMO:END -->", readme_demo(deck_data(report)["demo"])), encoding="utf-8")
