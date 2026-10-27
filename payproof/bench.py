"""Benchmark: PayProof pipeline vs a transparent rules-only baseline.

Run: python3 -m payproof.bench            (all cases, writes bench/results/latest.json + docs/BENCHMARK.md)
     python3 -m payproof.bench --smoke    (5 cases, no files written)

Ground truth (bench/ground_truth.json) is hand-computed and kept separate from outputs.
"""

import json
import statistics
import sys
import threading
import time
from pathlib import Path

from .actions import ActionError, ActionService, late_credit_note
from .evidence import EvidenceIndex
from .money import D, cents, fmt
from .sources import LocalFixtureSource, load_plans
from .workflow import investigate

ROOT = Path(__file__).resolve().parent.parent
SMOKE = ["CASE-1001", "CASE-1009", "CASE-1013", "CASE-1015", "CASE-1022"]


def baseline(case, plans):
    """Naive rules: CRM amount x CRM split (name-matched) x plan rate - paid. No evidence checks."""
    ix = EvidenceIndex(case)
    d = case["dispute"]
    emp = ix.get(d["employee_id"])
    opp = ix.get(d["opportunity_id"])
    users = [u for u in ix.of_type("crm_user") if u["name"].lower() == emp["name"].lower()]
    uid = users[0]["id"] if users else opp["owner"]
    splits = [s for s in ix.of_type("split") if s["opportunity_id"] == opp["id"] and s["crm_user_id"] == uid]
    pct = D(splits[0]["pct"]) if splits else D(100)
    version = next(v for v in plans["versions"] if v["effective_from"] <= opp["close_date"] <= v["effective_to"])
    due = cents(D(opp["amount"]) * pct / 100 * D(version["rate"]))
    paid = sum((D(l["amount"]) for l in ix.of_type("payroll_line") if l["employee_id"] == d["employee_id"]), D(0))
    delta = due - paid
    action = "PREPARE_PAYROLL_ADJUSTMENT" if delta > 0 else "FLAG_PAYOUT_REVIEW" if delta < 0 else "RECONCILIATION_REPORT"
    verdict = "REJECTED" if delta <= 0 else "SUPPORTED" if delta >= D(d["claimed_shortfall"]) else "PARTIALLY_SUPPORTED"
    return {"proof_status": "VERIFIED", "verdict": verdict, "action": action, "due": fmt(due), "paid": fmt(paid),
            "delta": fmt(delta), "citations": 0, "claims": 1}


def correct(r, g):
    """Status, verdict and action must match; money-moving or flagging actions must also carry the right amount."""
    ok = r["proof_status"] == g["proof_status"] and r["verdict"] == g["verdict"] and r["action"] == g["action"]
    if ok and g["action"] in ("PREPARE_PAYROLL_ADJUSTMENT", "FLAG_PAYOUT_REVIEW"):
        ok = r["delta"] == g["delta"]
    return ok


def score(rows, gt):
    n = len(rows)
    exact = sum(correct(r, gt[r["case_id"]]) for r in rows)
    money_err = []
    for r in rows:
        g = gt[r["case_id"]]
        if g["due"] is not None:
            money_err.append(abs(D(r["due"]) - D(g["due"])) if r["due"] is not None else None)
    measured = [e for e in money_err if e is not None]
    pos = lambda a: a == "PREPARE_PAYROLL_ADJUSTMENT"
    fp = sum(pos(r["action"]) and not pos(gt[r["case_id"]]["action"]) for r in rows)
    fn = sum(not pos(r["action"]) and pos(gt[r["case_id"]]["action"]) for r in rows)
    negatives = sum(not pos(g["action"]) for g in (gt[r["case_id"]] for r in rows))
    positives = n - negatives
    wrong_amount = sum(pos(r["action"]) and pos(gt[r["case_id"]]["action"]) and r["delta"] != gt[r["case_id"]]["delta"] for r in rows)
    abstain_needed = [r for r in rows if gt[r["case_id"]]["proof_status"] in ("NEEDS_EVIDENCE", "DISPUTED")]
    abstained = sum(r["proof_status"] in ("NEEDS_EVIDENCE", "DISPUTED") and r["action"] in ("REQUEST_EVIDENCE", "OPEN_DISPUTE")
                    for r in abstain_needed)
    false_abstain = sum(r["proof_status"] in ("NEEDS_EVIDENCE", "DISPUTED") for r in rows
                        if gt[r["case_id"]]["proof_status"] not in ("NEEDS_EVIDENCE", "DISPUTED"))
    return {
        "cases": n,
        "decision_accuracy": round(exact / n, 4), "decisions_correct": exact,
        "status_accuracy": round(sum(r["proof_status"] == gt[r["case_id"]]["proof_status"] for r in rows) / n, 4),
        "action_accuracy": round(sum(r["action"] == gt[r["case_id"]]["action"] for r in rows) / n, 4),
        "money_cases": len(money_err), "money_exact": sum(e == 0 for e in measured),
        "money_mean_abs_error": str(sum(measured, D(0)) / len(measured)) if measured else None,
        "money_max_abs_error": str(max(measured)) if measured else None,
        "adjustment_false_positives": fp, "adjustment_false_negatives": fn,
        "adjustment_fp_rate": round(fp / negatives, 4) if negatives else 0, "adjustment_fn_rate": round(fn / positives, 4) if positives else 0,
        "adjustments_with_wrong_amount": wrong_amount,
        "abstention_needed": len(abstain_needed), "correct_abstentions": abstained, "false_abstentions": false_abstain,
    }


def safety_suite(plans, gt, case_ids):
    svc = ActionService(LocalFixtureSource(), plans, audit_path=None)
    attempts = unauthorized_ok = 0
    dup_requests = 0
    stale_blocked = stale_total = 0
    failed_reported = 0
    for cid in case_ids:
        a = svc.propose(cid, "ana")
        if a["state"] != "AWAITING_APPROVAL":
            continue
        for tok in ("rep", "ana", "ops", "", "intruder"):
            attempts += 1
            try:
                svc.decide(a["id"], tok, True)
                unauthorized_ok += 1
            except ActionError:
                pass
        if a["required_permission"] == "controller":
            attempts += 1
            try:
                svc.decide(a["id"], "fin", True)
                unauthorized_ok += 1
            except ActionError:
                pass
        attempts += 1
        try:  # execution without approval
            svc.execute(a["id"], "ops", a["idempotency_key"])
            unauthorized_ok += 1
        except ActionError:
            pass
        svc.decide(a["id"], "ctl" if a["required_permission"] == "controller" else "fin", True)
        # concurrent duplicate execution
        threads = [threading.Thread(target=lambda: _quiet(svc.execute, a["id"], "ops", a["idempotency_key"])) for _ in range(5)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        dup_requests += 5
    rows_per_key = {}
    for r in svc.adapter.ledger + svc.adapter.tickets:
        rows_per_key[r["idempotency_key"]] = rows_per_key.get(r["idempotency_key"], 0) + 1
    duplicates = sum(c - 1 for c in rows_per_key.values() if c > 1)
    verified = sum(a["state"] == "VERIFIED" for a in svc.actions.values())

    # stale evidence: change sources after approval, before execution
    for cid in case_ids:
        s2 = ActionService(LocalFixtureSource(), plans, audit_path=None)
        a = s2.propose(cid, "ana")
        if a["state"] != "AWAITING_APPROVAL" or a["type"] != "PREPARE_PAYROLL_ADJUSTMENT":
            continue
        s2.decide(a["id"], "ctl" if a["required_permission"] == "controller" else "fin", True)
        case = s2.source.load_case(cid)
        inv = next(r for r in case["sources"]["billing"]["records"] if r["type"] == "invoice")
        rec = late_credit_note(cid)
        rec["invoice_id"] = inv["id"]
        s2.source.inject_late_event(cid, "billing", rec)
        stale_total += 1
        try:
            s2.execute(a["id"], "ops", a["idempotency_key"])
        except ActionError as e:
            stale_blocked += e.code == "STALE_EVIDENCE" and not s2.adapter.ledger
        # injected failure must not produce success
        s3 = ActionService(LocalFixtureSource(), plans, audit_path=None)
        a3 = s3.propose(cid, "ana")
        s3.decide(a3["id"], "ctl" if a3["required_permission"] == "controller" else "fin", True)
        s3.adapter.fail_next = True
        try:
            s3.execute(a3["id"], "ops", a3["idempotency_key"])
        except ActionError:
            failed_reported += a3["state"] == "FAILED" and a3["receipt"] is None
    post_total = post_receipts = 0
    for cid in case_ids:
        s4 = ActionService(LocalFixtureSource(), plans, audit_path=None)
        a4 = s4.propose(cid, "ana")
        if a4["state"] != "AWAITING_APPROVAL":
            continue
        s4.decide(a4["id"], "ctl" if a4["required_permission"] == "controller" else "fin", True)
        s4.verify_postcondition = lambda a, row: {"passed": False, "check": "forced failure"}
        post_total += 1
        try:
            s4.execute(a4["id"], "ops", a4["idempotency_key"])
        except ActionError:
            pass
        post_receipts += a4["receipt"] is not None or a4["state"] == "VERIFIED"
    return {"forced_postcondition_failures": post_total, "receipts_issued_despite_failed_postcondition": post_receipts,
            "unauthorized_attempts": attempts, "unauthorized_actions_succeeded": unauthorized_ok,
            "duplicate_execution_requests": dup_requests, "duplicate_actions_created": duplicates,
            "actions_verified": verified, "audit_chain_valid": svc.audit.verify_chain(),
            "stale_evidence_scenarios": stale_total, "stale_executions_blocked": stale_blocked,
            "injected_failures": stale_total, "failures_reported_honestly": failed_reported}


def _quiet(fn, *a):
    try:
        fn(*a)
    except ActionError:
        pass


def run(case_ids, write=True):
    plans = load_plans()
    gt = json.loads((ROOT / "bench" / "ground_truth.json").read_text())["cases"]
    src = LocalFixtureSource()
    agent_rows, base_rows, lat, per_case = [], [], [], []
    repro = 0
    cite_total = cite_ok = must_total = must_hit = narr_total = narr_unsupported = out_total = out_unsupported = 0
    model_modes = {}
    for cid in case_ids:
        case = src.load_case(cid)
        t0 = time.perf_counter()
        r = investigate(case, plans)
        lat.append((time.perf_counter() - t0) * 1000)
        r2 = investigate(src.load_case(cid), plans)
        repro += r["proof_hash"] == r2["proof_hash"]
        ix = EvidenceIndex(case)
        known = set(ix.records) | {v["id"] for v in plans["versions"]}
        material = r["bundle"] + [{"supporting": f["cites"]} for f in r["skeptic"]["findings"]]
        for m in material:
            cite_total += 1
            cite_ok += bool(m["supporting"]) and all(c in known for c in m["supporting"])
        cited = {c for m in material for c in m["supporting"]} | {c for b in r["bundle"] for c in b["contradicting"]}
        for must in gt[cid].get("must_cite", []):
            must_total += 1
            must_hit += must in cited
        narr_total += len(r["validation"]["accepted_narrative"]) + len(r["validation"]["unsupported_claims"])
        out_total += len(r["narrative"])
        out_unsupported += sum(not c["cites"] or any(x not in known | set(plans["clauses"]) for x in c["cites"]) for c in r["narrative"])
        narr_unsupported += len(r["validation"]["unsupported_claims"])
        for m in r["telemetry"]["model_calls"]:
            model_modes[m["model"]] = model_modes.get(m["model"], 0) + 1
        row = {"case_id": cid, "proof_status": r["proof_status"], "verdict": r["verdict"], "action": r["proposed_action"]["type"],
               "due": r["calculation"]["due"] if r["proof_status"] == "VERIFIED" else None, "paid": r["calculation"]["paid"],
               "delta": r["calculation"]["delta"] if r["proof_status"] == "VERIFIED" else None}
        agent_rows.append(row)
        b = baseline(case, plans)
        base_rows.append({"case_id": cid, **b})
        g = gt[cid]
        per_case.append({"case_id": cid, "title": case["title"], "expected": f"{g['proof_status']}/{g['action']}/{g['due']}",
                         "agent": f"{row['proof_status']}/{row['action']}/{row['due']}",
                         "baseline": f"{b['proof_status']}/{b['action']}/{b['due']}",
                         "agent_ok": correct(row, g), "baseline_ok": correct(b, g)})
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sample_size": len(case_ids), "dataset": "synthetic, hand-labelled (bench/ground_truth.json)",
        "agent": {**score(agent_rows, gt),
                  "citation_coverage": round(cite_ok / cite_total, 4) if cite_total else None,
                  "must_cite_recall": round(must_hit / must_total, 4) if must_total else None,
                  "narrative_claims": narr_total, "unsupported_claims_dropped": narr_unsupported,
                  "unsupported_claim_rate_in_output": round(out_unsupported / out_total, 4) if out_total else 0.0,
                  "reproducibility": round(repro / len(case_ids), 4),
                  "latency_ms_p50": round(statistics.median(lat), 2), "latency_ms_max": round(max(lat), 2),
                  "model_calls_by_model": model_modes},
        "baseline": {**score(base_rows, gt), "citation_coverage": 0.0,
                     "note": "Rules-only baseline: CRM amount x split x rate - all payroll lines; no evidence, identity, timing or conflict checks; no citations."},
        "safety": safety_suite(plans, gt, case_ids),
        "per_case": per_case,
        "limitations": [
            "Synthetic cases authored by the same team that wrote the policy engine; not an independent test set.",
            f"Sample size is {len(case_ids)} cases; rates are not statistically meaningful beyond this set.",
            "Model narration ran in deterministic-fallback mode unless model_calls_by_model shows a live model.",
            "The baseline is deliberately simple and transparent; it is not a competitor product.",
        ],
    }
    if write:
        out = ROOT / "bench" / "results"
        out.mkdir(parents=True, exist_ok=True)
        (out / "latest.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
        (ROOT / "docs" / "BENCHMARK.md").write_text(markdown(report))
        from .report import write_generated_docs
        write_generated_docs(report)  # deck + README numbers come from this run, never typed by hand
    return report


def markdown(r):
    a, b, s = r["agent"], r["baseline"], r["safety"]
    pct = lambda x: f"{x * 100:.1f}%" if isinstance(x, (int, float)) else str(x)
    lines = [
        "# Benchmark report", "",
        f"_Generated by `python3 -m payproof.bench` at {r['generated_at']}. Sample size: **{r['sample_size']} synthetic cases**, "
        "hand-labelled ground truth in `bench/ground_truth.json`. Numbers below are copied from `bench/results/latest.json`._", "",
        "## Agent pipeline vs rules-only baseline", "",
        "| Metric | PayProof | Baseline |", "|---|---|---|",
        f"| Decision accuracy (status + verdict + action, + amount when money moves) | {a['decisions_correct']}/{a['cases']} ({pct(a['decision_accuracy'])}) | {b['decisions_correct']}/{b['cases']} ({pct(b['decision_accuracy'])}) |",
        f"| Proof-status accuracy | {pct(a['status_accuracy'])} | {pct(b['status_accuracy'])} |",
        f"| Action-type accuracy | {pct(a['action_accuracy'])} | {pct(b['action_accuracy'])} |",
        f"| Exact due amount (cases with a determinable due) | {a['money_exact']}/{a['money_cases']} | {b['money_exact']}/{b['money_cases']} |",
        f"| Mean / max absolute due error | ${a['money_mean_abs_error']} / ${a['money_max_abs_error']} | ${b['money_mean_abs_error']} / ${b['money_max_abs_error']} |",
        f"| Payroll adjustments recommended wrongly (FP) | {a['adjustment_false_positives']} ({pct(a['adjustment_fp_rate'])}) | {b['adjustment_false_positives']} ({pct(b['adjustment_fp_rate'])}) |",
        f"| Payroll adjustments missed (FN) | {a['adjustment_false_negatives']} ({pct(a['adjustment_fn_rate'])}) | {b['adjustment_false_negatives']} ({pct(b['adjustment_fn_rate'])}) |",
        f"| Correct adjustments with wrong amount | {a['adjustments_with_wrong_amount']} | {b['adjustments_with_wrong_amount']} |",
        f"| Correct abstention (evidence insufficient/contradictory) | {a['correct_abstentions']}/{a['abstention_needed']} | {b['correct_abstentions']}/{b['abstention_needed']} |",
        f"| Evidence citation coverage (material claims) | {pct(a['citation_coverage'])} | {pct(b['citation_coverage'])} |",
        "", "## PayProof-only measurements", "",
        f"- Required-citation recall (`must_cite` records cited): {pct(a['must_cite_recall'])}",
        f"- Narrative claims produced: {a['narrative_claims']}; unsupported claims caught and dropped by the validator: {a['unsupported_claims_dropped']}; unsupported claims in final output: {a['unsupported_claim_rate_in_output']}",
        f"- Reproducibility (identical proof hash across two runs): {pct(a['reproducibility'])}",
        f"- Latency per investigation: p50 {a['latency_ms_p50']} ms, max {a['latency_ms_max']} ms (local, no network)",
        f"- Model calls by model: `{json.dumps(a['model_calls_by_model'])}`",
        "", "## Safety suite", "",
        f"- Unauthorized approval/execution attempts: {s['unauthorized_attempts']} — succeeded: **{s['unauthorized_actions_succeeded']}**",
        f"- Duplicate execution requests (5 concurrent per action): {s['duplicate_execution_requests']} — duplicate actions created: **{s['duplicate_actions_created']}**",
        f"- Actions executed and postcondition-verified: {s['actions_verified']}; audit hash chain valid: {s['audit_chain_valid']}",
        f"- Stale evidence injected between approval and execution: {s['stale_evidence_scenarios']} — executions blocked: **{s['stale_executions_blocked']}**",
        f"- Injected adapter failures: {s['injected_failures']} — reported as FAILED with no receipt: **{s['failures_reported_honestly']}**",
        f"- Forced postcondition failures: {s['forced_postcondition_failures']} — receipts issued anyway: **{s['receipts_issued_despite_failed_postcondition']}**",
        "", "## Per case", "", "| Case | Expected | PayProof | Baseline |", "|---|---|---|---|",
    ]
    for c in r["per_case"]:
        lines.append(f"| {c['case_id']} {c['title']} | {c['expected']} | {'✅' if c['agent_ok'] else '❌'} {c['agent']} | {'✅' if c['baseline_ok'] else '❌'} {c['baseline']} |")
    lines += ["", "## Limitations", ""] + [f"- {x}" for x in r["limitations"]] + [""]
    return "\n".join(lines)


def main():
    smoke = "--smoke" in sys.argv
    gt = json.loads((ROOT / "bench" / "ground_truth.json").read_text())["cases"]
    ids = SMOKE if smoke else sorted(gt)  # benchmark = hand-labelled cases only, never user-filed ones
    r = run(ids, write=not smoke)
    a, b, s = r["agent"], r["baseline"], r["safety"]
    print(f"cases={r['sample_size']}  agent accuracy={a['decisions_correct']}/{a['cases']}  baseline accuracy={b['decisions_correct']}/{b['cases']}")
    print(f"agent FP={a['adjustment_false_positives']} FN={a['adjustment_false_negatives']}  baseline FP={b['adjustment_false_positives']} FN={b['adjustment_false_negatives']}")
    print(f"unauthorized succeeded={s['unauthorized_actions_succeeded']}/{s['unauthorized_attempts']}  duplicates={s['duplicate_actions_created']}  "
          f"stale blocked={s['stale_executions_blocked']}/{s['stale_evidence_scenarios']}  reproducibility={a['reproducibility']}")
    if not smoke:
        print("wrote bench/results/latest.json and docs/BENCHMARK.md")
    ok = s["receipts_issued_despite_failed_postcondition"] == 0 and s["unauthorized_actions_succeeded"] == 0 and s["duplicate_actions_created"] == 0 and s["stale_executions_blocked"] == s["stale_evidence_scenarios"]
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
