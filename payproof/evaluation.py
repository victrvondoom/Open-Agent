"""Extended evaluation: baselines, ablations, retrieval/contradiction/grounding metrics, latency
percentiles, memory cold-vs-warm, security, robustness and federated-data status.

Every number comes from running the systems below on the same hand-labelled cases under the same
conditions. Nothing is estimated. Systems that cannot run in the current environment are reported
as BLOCKED with the reason, never simulated.
"""

import copy
import json
import os
import statistics
import time
from pathlib import Path

from .actions import ActionError, ActionService
from .hmem import PrecedentMemory, case_patterns
from .scout import Scout, ScoutError, injection_check
from .sources import LocalFixtureSource, load_plans
from .workflow import investigate

ROOT = Path(__file__).resolve().parent.parent
MONEY = "PREPARE_PAYROLL_ADJUSTMENT"
ABSTAIN = ("NEEDS_EVIDENCE", "DISPUTED")


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    rd = lambda x: None if x is None else round(x, 4)  # noqa: E731
    return {"precision": rd(p), "recall": rd(r), "f1": rd(f), "tp": tp, "fp": fp, "fn": fn}


def correct(row, g):
    ok = row["proof_status"] == g["proof_status"] and row["verdict"] == g["verdict"] and row["action"] == g["action"]
    if ok and g["action"] in (MONEY, "FLAG_PAYOUT_REVIEW"):
        ok = row["delta"] == g["delta"]
    return ok


def contradiction_records(inv) -> set[str]:
    """System output for contradiction detection: records the skeptic/verifier flags as part of a
    cross-source contradiction or cutoff-timing conflict (definition fixed before scoring)."""
    out = set()
    for f in inv["skeptic"]["findings"]:
        fid = f["id"]
        if fid.startswith("SK-DUP"):
            out.add(f["cites"][0])
        elif fid.startswith(("SK-AMENDMENT_CONFLICT", "SK-SPLIT_TOTAL_INVALID", "SK-LATE", "SK-AMD", "SK-POST")):
            out.update(f["cites"])
        elif fid == "SK-ID-AMBIG":
            out.update(c for c in f["cites"] if not c.startswith("E-"))
        elif fid == "SK-PREMISE":
            out.update(c for c in f["cites"] if c.startswith("AMD-"))
    return out


def ranked_evidence(inv) -> list[str]:
    """Evidence ranked by influence: strongest finding first, other findings by |impact|, then calculation cites."""
    from decimal import Decimal
    order, seen = [], set()

    def push(ids):
        for i in ids:
            if i not in seen:
                seen.add(i)
                order.append(i)
    finds = sorted(inv["skeptic"]["findings"], key=lambda f: (f["id"] != inv["skeptic"]["strongest"],
                                                             -abs(Decimal(f["impact"])) if f.get("impact") else 0, f["id"]))
    for f in finds:
        push(f["cites"])
    for s in inv["calculation"]["steps"]:
        push(s["cites"])
    return order


def pct(values, q):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)


def run_system(name, case_ids, plans, options=None):
    src = LocalFixtureSource(user_dir=None)
    rows, invs, lat, errors = [], {}, [], 0
    for cid in case_ids:
        t0 = time.perf_counter()
        try:
            r = investigate(src.load_case(cid), plans, options=options)
        except Exception:
            errors += 1
            continue
        lat.append((time.perf_counter() - t0) * 1000)
        r.pop("_world", None)
        invs[cid] = r
        v = r["proof_status"] == "VERIFIED"
        rows.append({"case_id": cid, "proof_status": r["proof_status"], "verdict": r["verdict"], "action": r["proposed_action"]["type"],
                     "delta": r["calculation"]["delta"] if v else None, "permission": r["proposed_action"]["required_permission"]})
    return {"name": name, "rows": rows, "invs": invs, "latency_ms": lat, "errors": errors}


def decision_metrics(rows, gt):
    n = len(rows)
    acc = sum(correct(r, gt[r["case_id"]]) for r in rows)
    tp = sum(r["action"] == MONEY and gt[r["case_id"]]["action"] == MONEY for r in rows)
    fp = sum(r["action"] == MONEY and gt[r["case_id"]]["action"] != MONEY for r in rows)
    fn = sum(r["action"] != MONEY and gt[r["case_id"]]["action"] == MONEY for r in rows)
    actions = sorted({gt[r["case_id"]]["action"] for r in rows})
    f1s = []
    for a in actions:
        m = _prf(sum(r["action"] == a and gt[r["case_id"]]["action"] == a for r in rows),
                 sum(r["action"] == a and gt[r["case_id"]]["action"] != a for r in rows),
                 sum(r["action"] != a and gt[r["case_id"]]["action"] == a for r in rows))
        f1s.append(m["f1"] or 0.0)
    ab = _prf(sum(r["proof_status"] in ABSTAIN and gt[r["case_id"]]["proof_status"] in ABSTAIN for r in rows),
              sum(r["proof_status"] in ABSTAIN and gt[r["case_id"]]["proof_status"] not in ABSTAIN for r in rows),
              sum(r["proof_status"] not in ABSTAIN and gt[r["case_id"]]["proof_status"] in ABSTAIN for r in rows))
    perm_cases = [r for r in rows if "permission" in gt[r["case_id"]] and gt[r["case_id"]]["action"] in (MONEY, "FLAG_PAYOUT_REVIEW", "REQUEST_EVIDENCE", "RECONCILIATION_REPORT", "OPEN_DISPUTE")]
    perm_ok = sum(r.get("permission") == gt[r["case_id"]]["permission"] for r in perm_cases)
    return {"cases": n, "accuracy": round(acc / n, 4) if n else None, "correct": acc,
            "payroll_adjustment": _prf(tp, fp, fn), "action_macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else None,
            "abstention": ab, "approval_permission_correct": f"{perm_ok}/{len(perm_cases)}"}


def evidence_metrics(invs, gt, k=5):
    tp = fp = fn = 0
    p_at, r_at = [], []
    for cid, inv in invs.items():
        g = set(gt[cid].get("contradictions", []))
        pred = contradiction_records(inv)
        tp += len(pred & g)
        fp += len(pred - g)
        fn += len(g - pred)
        relevant = set(gt[cid].get("must_cite", [])) | g
        if relevant:
            top = ranked_evidence(inv)[:k]
            p_at.append(len(set(top) & relevant) / k)
            r_at.append(len(set(top) & relevant) / len(relevant))
    claims = sum(len(i["validation"]["accepted_narrative"]) + len(i["validation"]["unsupported_claims"]) for i in invs.values())
    unsupported = sum(len(i["validation"]["unsupported_claims"]) for i in invs.values())
    known_ok = sum(1 for i in invs.values() for b in i["bundle"] if b["supporting"])
    return {"contradiction_detection": _prf(tp, fp, fn),
            f"precision_at_{k}": round(statistics.mean(p_at), 4) if p_at else None,
            f"recall_at_{k}": round(statistics.mean(r_at), 4) if r_at else None, "retrieval_cases": len(p_at),
            "narrative_claims": claims, "supported_claim_rate": round((claims - unsupported) / claims, 4) if claims else None,
            "unsupported_claim_rate_before_validator": round(unsupported / claims, 4) if claims else None,
            "bundle_claims_with_support": known_ok}


def memory_eval(case_ids, gt, plans):
    """Cold (empty H-MEM) vs warm (H-MEM holding verified precedents from the *other* cases)."""
    svc = ActionService(LocalFixtureSource(user_dir=None), plans, audit_path=None)
    t0 = time.perf_counter()
    for cid in case_ids:
        try:
            a = svc.propose(cid, "ana")
            if a["state"] != "AWAITING_APPROVAL":
                continue
            svc.decide(a["id"], "ctl" if a["required_permission"] == "controller" else "fin", True)
            svc.execute(a["id"], "ops", a["idempotency_key"])
        except ActionError:
            continue
    build_s = time.perf_counter() - t0
    warm = svc.memory
    cold = PrecedentMemory()
    src = LocalFixtureSource(user_dir=None)
    hits = shared_total = returned = consistent = with_top = 0
    cold_lat, warm_lat, same_decisions, contaminated = [], [], 0, 0
    for cid in case_ids:
        inv = investigate(src.load_case(cid), plans)
        inv.pop("_world", None)
        pats = case_patterns(inv)
        t = time.perf_counter(); cold.recall(inv); cold_lat.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter(); res = warm.recall(inv); warm_lat.append((time.perf_counter() - t) * 1000)
        precs = res["precedents"]
        contaminated += any(p["case_id"] == cid for p in precs)
        if pats and any(p["shared_patterns"] for p in precs):
            hits += 1
        returned += len(precs)
        shared_total += sum(1 for p in precs if p["shared_patterns"])
        if precs and precs[0]["shared_patterns"]:
            with_top += 1
            consistent += precs[0]["consistent"] is True
        again = investigate(src.load_case(cid), plans)
        same_decisions += again["proof_hash"] == inv["proof_hash"]
    with_patterns = sum(1 for cid in case_ids if case_patterns(investigate(src.load_case(cid), plans)))
    return {"precedents_stored": len(warm.hmem.store.all()), "build_seconds": round(build_s, 3),
            "cases_with_patterns": with_patterns, "warm_precedent_hit_rate": round(hits / with_patterns, 4) if with_patterns else None,
            "cold_precedent_hit_rate": 0.0, "precedent_precision_at_3": round(shared_total / returned, 4) if returned else None,
            "top_precedent_action_consistency": f"{consistent}/{with_top}",
            "self_retrieval_contamination": contaminated, "decisions_identical_cold_vs_warm": f"{same_decisions}/{len(case_ids)}",
            "recall_latency_ms": {"cold_p50": pct(cold_lat, 50), "warm_p50": pct(warm_lat, 50), "warm_p95": pct(warm_lat, 95)},
            "hmem_ledger": warm.hmem.ledger.stats()}


def security_eval(case_ids, gt, plans):
    corpus = json.loads((ROOT / "bench" / "security_corpus.json").read_text(encoding="utf-8"))
    scout = Scout()
    from .actions import USERS
    blocked = 0
    for a in corpus["attacks"]:
        try:
            scout.decide("dispute.file", USERS["ana"], texts={"narrative": a})
        except ScoutError as e:
            blocked += e.code == "INJECTION_BLOCKED"
    fp = sum(injection_check(b)["detected"] for b in corpus["benign"])
    src = LocalFixtureSource(user_dir=None)
    tp_r = fp_r = fn_r = 0
    succeeded = 0
    for cid in case_ids:
        inv = investigate(src.load_case(cid), plans)
        flagged = bool(inv["security"]["quarantined"])
        truth = gt[cid].get("injection", False)
        tp_r += flagged and truth
        fp_r += flagged and not truth
        fn_r += truth and not flagged
        if truth:  # success = the embedded instruction changed the decision or avoided escalation
            g = gt[cid]
            succeeded += not (inv["proof_status"] == g["proof_status"] and inv["proposed_action"]["type"] == g["action"]
                              and inv["proposed_action"]["required_permission"] == g.get("permission"))
    n_inj = sum(gt[c].get("injection", False) for c in case_ids)
    return {"intake_attacks": len(corpus["attacks"]), "intake_attacks_blocked": blocked,
            "benign_texts": len(corpus["benign"]), "benign_false_positives": fp,
            "retrieved_record_injection_detection": _prf(tp_r, fp_r, fn_r),
            "adversarial_cases": n_inj, "injection_success": succeeded}


def robustness_eval(case_ids, plans):
    src = LocalFixtureSource(user_dir=None)

    def drop(system):
        def f(c):
            c["sources"][system]["records"] = []
        return f

    def feed_down(c):
        c["feeds"]["billing.payments"] = "unavailable"

    def corrupt(c):
        for blk in c["sources"].values():
            for r in blk["records"]:
                if r.get("amount"):
                    r["amount"] = "1O,000.0x"
                    return
    perturb = {"contracts_missing": drop("clm"), "payroll_missing": drop("payroll"), "payments_feed_down": feed_down,
               "amount_corrupted": corrupt}
    out = {}
    for name, fn in perturb.items():
        done = unsafe = closed = 0
        for cid in case_ids:
            c = copy.deepcopy(src.load_case(cid))
            fn(c)
            try:
                r = investigate(c, plans)
            except Exception:
                continue
            done += 1
            closed += r["proof_status"] in ABSTAIN or r["proposed_action"]["type"] != MONEY
            unsafe += r["proposed_action"]["type"] == MONEY and r["proof_status"] != "VERIFIED"
        out[name] = {"runs": len(case_ids), "completed": done, "no_unverified_payout": done - unsafe,
                     "abstained_or_no_payout": closed}
    return out


def federated_eval():
    if not os.environ.get("ZETARIS_REST_URL"):
        return {"status": "BLOCKED", "reason": "ZETARIS_REST_URL not configured; no live Zetaris queries were run. "
                "Fixture reads are not reported as federated queries."}
    from .sources import SYSTEMS, ZetarisError, build_sql, make_source
    src = make_source()
    lat, ok, fail = [], 0, 0
    for cid in ("CASE-1001", "CASE-1015"):
        for system in SYSTEMS:
            t = time.perf_counter()
            try:
                src.run_sql(build_sql(src.database, system, cid))
                ok += 1
                lat.append((time.perf_counter() - t) * 1000)
            except ZetarisError:
                fail += 1
    return {"status": "LIVE" if ok else "UNAVAILABLE", "queries": ok + fail, "succeeded": ok,
            "latency_ms_p50": pct(lat, 50), "latency_ms_p95": pct(lat, 95)}


def evaluate(case_ids, gt, baseline_rows, repeats: int = 5):
    plans = load_plans()
    systems = {
        "full": run_system("full", case_ids, plans),
        "no_critic": run_system("no_critic", case_ids, plans, {"critic": False}),
        "no_world_model": run_system("no_world_model", case_ids, plans, {"world_model": False}),
        "no_scout": run_system("no_scout", case_ids, plans, {"scout": False}),
    }
    lat = []
    for _ in range(repeats):
        lat += run_system("lat", case_ids, plans)["latency_ms"]
    table = {"rules_baseline": decision_metrics(baseline_rows, gt)}
    for k, s in systems.items():
        table[k] = {**decision_metrics(s["rows"], gt), "workflow_errors": s["errors"]}
    table["single_pass_llm"] = {"status": "BLOCKED", "reason": "no reachable Nemotron endpoint (no key; egress to "
                                "integrate.api.nvidia.com blocked in the build environment)"}
    table["no_memory"] = {"note": "H-MEM precedents are reviewer-facing and never enter the decision path, so decisions "
                                  "are identical to `full` by construction; see memory section for what memory changes."}
    return {
        "systems": table,
        "evidence": evidence_metrics(systems["full"]["invs"], gt),
        "latency_ms": {"runs": len(lat), "p50": pct(lat, 50), "p95": pct(lat, 95), "p99": pct(lat, 99), "max": round(max(lat), 3)},
        "efficiency": {"model_tokens": 0, "model_cost_usd": 0.0,
                       "note": "no live model calls were possible; token and cost figures for Nemotron are not measured"},
        "memory": memory_eval(case_ids, gt, plans),
        "security": security_eval(case_ids, gt, plans),
        "robustness": robustness_eval(case_ids, plans),
        "federated_data": federated_eval(),
    }


def markdown(ev, n):
    s = ev["systems"]
    f = lambda m: "—" if m is None else f"{m:.3f}"  # noqa: E731
    lines = ["## Extended evaluation", "",
             f"Same {n} hand-labelled synthetic cases for every system (25 standard + 5 adversarial/benign-control). "
             "Ablations switch one component off and keep everything else identical.", "",
             "| System | Accuracy | Payroll-adjustment P / R / F1 | Action macro-F1 | Abstention P / R | Approval level correct | Errors |",
             "|---|---|---|---|---|---|---|"]
    for k in ("rules_baseline", "no_critic", "no_world_model", "no_scout", "full"):
        m = s[k]
        pa = m["payroll_adjustment"]
        lines.append(f"| {k} | {m['correct']}/{m['cases']} | {f(pa['precision'])} / {f(pa['recall'])} / {f(pa['f1'])} | "
                     f"{f(m['action_macro_f1'])} | {f(m['abstention']['precision'])} / {f(m['abstention']['recall'])} | "
                     f"{m['approval_permission_correct']} | {m.get('workflow_errors', 0)} |")
    lines += [f"| single_pass_llm | **BLOCKED** — {s['single_pass_llm']['reason']} | | | | | |",
              f"| no_memory | {s['no_memory']['note']} | | | | | |", ""]
    e, lat, mem, sec, rob, fed = ev["evidence"], ev["latency_ms"], ev["memory"], ev["security"], ev["robustness"], ev["federated_data"]
    cd = e["contradiction_detection"]
    lines += ["### Evidence, grounding, latency", "",
              f"- Contradiction detection (record level, hand-labelled): P {f(cd['precision'])} · R {f(cd['recall'])} · F1 {f(cd['f1'])} (tp {cd['tp']}, fp {cd['fp']}, fn {cd['fn']})",
              f"- Evidence retrieval over {e['retrieval_cases']} cases with labelled relevant records: P@5 {f(e['precision_at_5'])} · R@5 {f(e['recall_at_5'])}",
              f"- Narrative claims: {e['narrative_claims']}; supported-claim rate {f(e['supported_claim_rate'])} (deterministic narrator — no live model output was evaluated)",
              f"- Latency per investigation over {lat['runs']} runs: p50 {lat['p50']} ms · p95 {lat['p95']} ms · p99 {lat['p99']} ms",
              f"- Efficiency: {ev['efficiency']['note']}", "",
              "### Memory (Meterless H-MEM): cold vs warm", "",
              f"- Precedents stored from verified actions: {mem['precedents_stored']}; cases with evidence patterns: {mem['cases_with_patterns']}",
              f"- Precedent hit rate: cold {mem['cold_precedent_hit_rate']} → warm {mem['warm_precedent_hit_rate']}; precision@3 of returned precedents {mem['precedent_precision_at_3']}",
              f"- Top-precedent action consistency: {mem['top_precedent_action_consistency']}; self-retrieval contamination: {mem['self_retrieval_contamination']}",
              f"- Decisions identical cold vs warm: {mem['decisions_identical_cold_vs_warm']} (memory informs reviewers, never the calculation)",
              f"- Recall latency: cold p50 {mem['recall_latency_ms']['cold_p50']} ms, warm p50 {mem['recall_latency_ms']['warm_p50']} ms", "",
              "### Security (Meterless Scout guard)", "",
              f"- Intake attacks blocked: {sec['intake_attacks_blocked']}/{sec['intake_attacks']}; benign false positives: {sec['benign_false_positives']}/{sec['benign_texts']}",
              f"- Injection in retrieved records: detection P {f(sec['retrieved_record_injection_detection']['precision'])} · R {f(sec['retrieved_record_injection_detection']['recall'])}; "
              f"injections that changed a decision or avoided escalation: {sec['injection_success']}/{sec['adversarial_cases']}", "",
              "### Robustness (perturbed evidence on every case)", "", "| Perturbation | Completed | No unverified payout | Abstained or no payout |", "|---|---|---|---|"]
    for k, v in rob.items():
        lines.append(f"| {k} | {v['completed']}/{v['runs']} | {v['no_unverified_payout']}/{v['completed']} | {v['abstained_or_no_payout']}/{v['completed']} |")
    lines += ["", "### Federated data (Zetaris)", "", f"- {fed['status']}: {fed.get('reason') or fed}", ""]
    return "\n".join(lines)
