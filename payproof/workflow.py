"""Bounded, auditable investigation workflow.

    Investigator -> Skeptic -> Policy verifier -> Resolution planner -> Final validator

Fixed order, no loops, at most MAX_CALLS_PER_RUN model calls. Model output is
narrative only; status, money and actions come from deterministic code.
"""

import re
import time

from . import ENGINE_VERSION
from .counterfactual import replay
from .evidence import EvidenceIndex, build_graph, resolve_identity
from .llm import ModelClient
from .meterless import rank_scenarios
from .money import D, cents, fmt
from .policy import Scenario, compute
from .sources import sha

ACTION_TYPES = {"REQUEST_EVIDENCE", "OPEN_DISPUTE", "PREPARE_PAYROLL_ADJUSTMENT", "FLAG_PAYOUT_REVIEW", "RECONCILIATION_REPORT"}


def source_fingerprint(case: dict) -> str:
    return sha({"sources": case["sources"], "feeds": case["feeds"], "dispute": case["dispute"]})


# --------------------------------------------------------------------------- helpers

def _step(calc, key):
    return next((s for s in calc["steps"] if s["key"] == key), None)


def _money(x):
    return f"${D(x):,.2f}" if x is not None else "n/a"


def timeline(index, cutoff):
    events = []
    for rid, r in index.records.items():
        if r.get("type") in ("crm_user", "employee", "payroll_batch") or not r.get("effective_at"):
            continue
        eff, rec = r["effective_at"][:10], (r.get("recorded_at") or "")[:10]
        flags = []
        if eff <= cutoff < rec:
            flags.append("LATE_ARRIVING")
        if eff > cutoff:
            flags.append("AFTER_CUTOFF")
        if r.get("type") == "amendment" and r["signed_date"] > cutoff:
            flags.append("SIGNED_AFTER_CUTOFF")
        events.append({"record_id": rid, "type": r.get("type", "dispute"), "system": index.system_of[rid],
                       "effective_at": eff, "recorded_at": rec, "amount": r.get("amount") or r.get("tcv") or r.get("new_tcv"),
                       "flags": flags})
    events.append({"record_id": "CUTOFF", "type": "cutoff", "system": "payroll", "effective_at": cutoff,
                   "recorded_at": cutoff, "amount": None, "flags": []})
    return sorted(events, key=lambda e: (e["effective_at"], e["type"] != "cutoff", e["record_id"]))


# --------------------------------------------------------------------------- roles

def investigator(index, calc, identity):
    d = index.case["dispute"]
    opp = index.get(d["opportunity_id"])
    rate = _step(calc, "rate")
    claims = []
    premise = None
    if opp and rate:
        sp = _step(calc, "split")
        premise = cents(D(opp["amount"]) * D(sp["pct"]) / 100 * D(rate["value"]))
        claims.append({"text": f"Claimant premise: CRM amount {_money(opp['amount'])} x split {sp['pct']}% x rate {rate['value']} = {_money(premise)} expected.",
                       "cites": [opp["id"], rate["plan_version"]]})
    if calc["blockers"]:
        h = "Payout cannot be determined yet: " + "; ".join(b["detail"] for b in calc["blockers"]) + "."
        claims.append({"text": h, "cites": [c for b in calc["blockers"] for c in b["cites"]] or [d["id"]]})
    else:
        base = _step(calc, "base")
        if base:
            claims.append({"text": f"Commission due is {_money(calc['due'])} on a commissionable base of {_money(base['value'])}; "
                                   f"{_money(calc['paid'])} has been paid.",
                           "cites": _step(calc, "eligible")["cites"] + _step(calc, "collected")["cites"] + _step(calc, "paid")["cites"]})
        else:
            claims.append({"text": f"Opportunity is not commissionable; {_money(calc['paid'])} paid.", "cites": [opp["id"]]})
        if calc["delta"] is not None:
            dl = D(calc["delta"])
            word = "underpaid" if dl > 0 else "overpaid" if dl < 0 else "paid correctly"
            claims.append({"text": f"Initial hypothesis: claimant was {word} by {_money(abs(dl))}.",
                           "cites": [d["id"]] + _step(calc, "paid")["cites"]})
    return {"statement": claims[-1]["text"], "claims": claims, "premise": fmt(premise) if premise is not None else None,
            "waterfall": waterfall(index, calc)}


def waterfall(index, calc):
    """Deterministic bridge from the claimant's expectation to the verified variance."""
    d = index.case["dispute"]
    opp = index.get(d["opportunity_id"])
    elig, base, rate, split = (_step(calc, k) for k in ("eligible", "base", "rate", "split"))
    if not (opp and elig and base and rate and split) or calc["due"] is None:
        return None
    pct, r = D(split["pct"]) / 100, D(rate["value"])
    crm = D(opp["amount"])
    rows = [{"label": "Claimant expectation: CRM amount x split x rate", "amount": fmt(crm * pct * r), "kind": "start",
             "cites": [opp["id"]] + split["cites"]}]
    if D(elig["value"]) != crm:
        rows.append({"label": "Eligible contract value differs from CRM amount (P-3.1)", "amount": fmt((D(elig["value"]) - crm) * pct * r),
                     "kind": "step", "cites": elig["cites"]})
    if D(base["value"]) != D(elig["value"]):
        rows.append({"label": "Collection basis: only net cash collected by cutoff is commissionable (P-3.2)",
                     "amount": fmt((D(base["value"]) - D(elig["value"])) * pct * r), "kind": "step", "cites": _step(calc, "collected")["cites"]})
    exact = D(base["value"]) * pct * r
    if cents(exact) != exact:
        rows.append({"label": "Rounding (half-up, once)", "amount": fmt(cents(exact) - exact), "kind": "step", "cites": []})
    rows.append({"label": "Verified commission due", "amount": calc["due"], "kind": "subtotal", "cites": []})
    for c in _step(calc, "paid")["cites"]:
        rec = index.get(c)
        if rec:
            rows.append({"label": f"Paid: {rec['line_type']} {c}" + (f" ({rec['memo']})" if rec.get("memo") else ""),
                         "amount": fmt(-D(rec["amount"])), "kind": "step", "cites": [c]})
        else:
            rows.append({"label": f"Paid: simulated adjustment {c}", "amount": None, "kind": "step", "cites": [c]})
    rows.append({"label": "Verified variance (due - paid)", "amount": calc["delta"], "kind": "total", "cites": []})
    return rows


def skeptic(index, calc, identity, cfs, tl):
    """Search for evidence that would falsify the investigator's conclusion."""
    findings = []
    d = index.case["dispute"]
    by_id = {c["id"]: c for c in cfs}

    def f(fid, title, detail, cites, outcome, cf=None, severity="medium", rule=None):
        findings.append({"id": fid, "title": title, "detail": detail, "cites": cites, "outcome": outcome,
                         "counterfactual": cf, "impact": by_id[cf]["delta_change"] if cf in by_id else None,
                         "severity": severity, "rule": rule})

    # identity
    emp = index.get(d["employee_id"])
    for c in identity["candidates"]:
        if c["strength"] == "STRONG" and c["name"] != emp["name"]:
            f("SK-ID-NAME", f"CRM user {c['crm_user_id']} name '{c['name']}' differs from HRIS '{emp['name']}'",
              f"Linked on {c['signals'][0]}; name difference alone does not break the link.", [emp["id"], c["crm_user_id"]], "RULED_OUT",
              severity="low")
    if identity["status"] != "RESOLVED":
        f("SK-ID-AMBIG", "Claimant identity cannot be uniquely linked to CRM",
          f"{len(identity['candidates'])} weak candidate(s), no email/alias match. Not merged.",
          [emp["id"]] + [c["crm_user_id"] for c in identity["candidates"]], "UNRESOLVED", severity="high")

    # late-arriving / post-cutoff
    for e in tl:
        if "LATE_ARRIVING" in e["flags"] and e["type"] in ("payment", "credit_note", "refund"):
            f(f"SK-LATE-{e['record_id']}", f"{e['record_id']} was recorded {e['recorded_at']}, after the cutoff",
              f"Value date {e['effective_at']} is before cutoff. If recording date governed, it would be excluded. "
              f"P-4.2 says value date governs, so it is included.", [e["record_id"]], "RULED_OUT", cf="cf_recorded_timing",
              severity="high", rule="P-4.2")
        if "SIGNED_AFTER_CUTOFF" in e["flags"]:
            f(f"SK-AMD-{e['record_id']}", f"Amendment {e['record_id']} signed after cutoff (backdated effective date)",
              "Excluded under P-3.1; the claimant's higher value depends on it.", [e["record_id"]], "CONFIRMED",
              cf=f"cf_amend_signed_{e['record_id']}", severity="high", rule="P-3.1")
        elif "AFTER_CUTOFF" in e["flags"] and e["type"] in ("payment", "credit_note", "refund"):
            f(f"SK-POST-{e['record_id']}", f"{e['record_id']} falls after the cutoff",
              "Excluded from this period's calculation.", [e["record_id"]], "CONFIRMED",
              cf=next((c["id"] for c in cfs if e["record_id"] in c["changed_facts"]), None), rule="P-4.2")

    # claimant premise vs eligible value
    opp = index.get(d["opportunity_id"])
    elig = _step(calc, "eligible")
    if elig and opp and D(opp["amount"]) != D(elig["value"]):
        f("SK-PREMISE", f"CRM amount {_money(opp['amount'])} is not the eligible value {_money(elig['value'])}",
          "The claim appears to rely on the CRM opportunity amount rather than the amended contract.",
          [opp["id"]] + elig["cites"], "CONFIRMED", cf=next((c["id"] for c in cfs if c["id"].startswith("cf_no_amend")), None),
          rule="P-3.1")
    coll = _step(calc, "collected")
    if coll and elig and D(coll["value"]) < D(elig["value"]):
        f("SK-PARTIAL", f"Only {_money(coll['value'])} collected against {_money(elig['value'])} eligible",
          "Collection basis caps the commissionable base.", coll["cites"], "CONFIRMED",
          cf=next((c["id"] for c in cfs if c["id"].startswith("cf_full_payment")), None), rule="P-3.2")

    # duplicates
    for c in cfs:
        if c["id"].startswith("cf_dedupe_"):
            f(f"SK-DUP-{c['changed_facts'][0]}", f"Payroll line {c['changed_facts'][0]} duplicates {c['changed_facts'][1]}",
              "Same type, reference and amount posted twice.", c["changed_facts"], "CONFIRMED", cf=c["id"], severity="high")

    # conflicts
    for c in calc["conflicts"]:
        f(f"SK-{c['code']}", c["detail"], "Contradictory source records.", c["cites"], "UNRESOLVED", severity="high")

    # exceptions
    for st in calc["steps"]:
        for ex in st["excluded"]:
            if ex["id"].startswith("EXC"):
                f(f"SK-EXC-{ex['id']}", f"Rate exception {ex['id']} is not approved", ex["reason"], [ex["id"]], "CONFIRMED",
                  cf=f"cf_exc_{ex['id']}", rule="P-5.1")

    against = [x for x in findings if x["impact"] and D(x["impact"]) != 0]
    strongest = max(against, key=lambda x: (abs(D(x["impact"])), x["id"]), default=None)
    unresolved = [x for x in findings if x["outcome"] == "UNRESOLVED"]
    if unresolved:
        strongest = unresolved[0]
    return {"findings": findings, "strongest": strongest["id"] if strongest else None}


def policy_verifier(index, plans, identity, calc, ledger=()):
    """Independently recompute from cited records and check invariants."""
    inv = []
    ledger_by_id = {l["id"]: l for l in ledger}

    def check(name, ok, detail=""):
        inv.append({"invariant": name, "passed": bool(ok), "detail": detail})

    all_cites = [c for s in calc["steps"] for c in s["cites"]]
    missing = [c for c in all_cites if not index.exists(c) and c not in ledger_by_id
               and c not in {pv["id"] for pv in plans["versions"]}]
    check("every calculation citation resolves to a real record", not missing, ", ".join(missing))

    paid_step = _step(calc, "paid")
    recomputed_paid = sum((D((index.get(c) or ledger_by_id.get(c))["amount"]) for c in paid_step["cites"]
                           if index.exists(c) or c in ledger_by_id), D(0))
    check("paid recomputes from cited payroll lines", recomputed_paid == D(paid_step["value"]),
          f"{fmt(recomputed_paid)} vs {paid_step['value']}")

    coll = _step(calc, "collected")
    if coll:
        total = D(0)
        for c in coll["cites"]:
            r = index.get(c)
            if r and r["type"] == "payment":
                total += D(r["amount"])
            elif r and r["type"] in ("refund", "credit_note"):
                total -= D(r["amount"])
        check("net collected recomputes from cited payments/refunds/credit notes", total == D(coll["value"]),
              f"{fmt(total)} vs {coll['value']}")
    base, elig, due = _step(calc, "base"), _step(calc, "eligible"), _step(calc, "due")
    if base and elig and coll:
        check("base = max(0, min(eligible, collected))", D(base["value"]) == max(D(0), min(D(elig["value"]), D(coll["value"]))))
    if due and base:
        pct = D(_step(calc, "split")["pct"])
        rate = D(_step(calc, "rate")["value"])
        check("due = round_half_up(base x split x rate)", D(due["value"]) == cents(D(base["value"]) * pct / 100 * rate))
    if calc["delta"] is not None:
        check("delta = due - paid", D(calc["delta"]) == D(calc["due"]) - D(calc["paid"]))
    money_vals = [s["value"] for s in calc["steps"] if s["key"] in ("due", "paid", "base", "collected", "eligible", "delta")]
    check("monetary values are exact 2-dp decimal strings", all(re.fullmatch(r"-?\d+\.\d{2}", v) for v in money_vals))

    # materiality of conflicts by recomputation
    conflicts = []
    for c in calc["conflicts"]:
        c = dict(c)
        if c["key"] == "amendment":
            dues = {compute(index, plans, identity, Scenario(id="m", choose={"amendment": o}))["due"] for o in c["options"]}
            c["material"] = len(dues) > 1
            c["alternative_dues"] = sorted(dues)
        conflicts.append(c)

    failed = [i for i in inv if not i["passed"]]
    if failed:
        status = "REJECTED"
    elif calc["blockers"]:
        status = "NEEDS_EVIDENCE"
    elif any(c["material"] for c in conflicts):
        status = "DISPUTED"
    else:
        status = "VERIFIED"
    return {"invariants": inv, "conflicts": conflicts, "proof_status": status}


def verdict_for(status, calc, claimed):
    if status != "VERIFIED":
        return "UNDETERMINED"
    delta = D(calc["delta"])
    if delta <= 0:
        return "REJECTED"
    return "SUPPORTED" if delta >= D(claimed) else "PARTIALLY_SUPPORTED"


def resolution_planner(index, plans, status, verdict, calc, fingerprint, run_id, findings):
    d = index.case["dispute"]
    paid_cites = _step(calc, "paid")["cites"] if _step(calc, "paid") else []
    limits = plans["approval_limits"]
    amount, perm = None, "finance_approver"
    if status == "NEEDS_EVIDENCE":
        typ = "REQUEST_EVIDENCE"
        justification = "; ".join(b["detail"] for b in calc["blockers"])
        expected = "Evidence request ticket opened with source-system owners; no payout change."
        affected = [c for b in calc["blockers"] for c in b["cites"]] or [d["id"]]
    elif status == "DISPUTED":
        typ = "OPEN_DISPUTE"
        justification = "Material contradiction in source records: " + "; ".join(c["detail"] for c in calc["conflicts"])
        expected = "Formal dispute opened for source-record owners; no payout change until resolved."
        affected = [x for c in calc["conflicts"] for x in c["cites"]]
    elif status == "VERIFIED" and D(calc["delta"]) > 0:
        typ, amount = "PREPARE_PAYROLL_ADJUSTMENT", calc["delta"]
        perm = "finance_approver" if D(amount) <= D(limits["finance_approver"]) else "controller"
        dup = [f for f in findings if f["id"].startswith("SK-DUP")]
        justification = (f"Verified commission due {_money(calc['due'])} exceeds paid {_money(calc['paid'])}"
                         + (f"; includes reversal of duplicate line {dup[0]['cites'][0]}" if dup else ""))
        expected = f"Paid total for {d['employee_id']}/{d['opportunity_id']} becomes {_money(calc['due'])}; variance 0.00."
        affected = paid_cites
    elif status == "VERIFIED" and D(calc["delta"]) < 0:
        typ, amount = "FLAG_PAYOUT_REVIEW", fmt(-D(calc["delta"]))
        justification = f"Paid {_money(calc['paid'])} exceeds verified due {_money(calc['due'])}; overpayment flagged for review (no automatic clawback)."
        expected = "Overpayment review ticket opened; no money moved."
        affected = paid_cites
    elif status == "VERIFIED":
        typ = "RECONCILIATION_REPORT"
        justification = f"Payout of {_money(calc['paid'])} matches verified due; claim not supported."
        expected = "Reconciliation report delivered to claimant and manager; no payout change."
        affected = paid_cites or [d["id"]]
    else:
        typ = "REQUEST_EVIDENCE"
        justification = "Verification failed; recompute required."
        expected = "No payout change."
        affected = [d["id"]]
    return {
        "type": typ, "case_id": index.case["case_id"], "employee_id": d["employee_id"], "opportunity_id": d["opportunity_id"],
        "amount": amount, "justification": justification, "affected_records": sorted(set(affected)),
        "expected_result": expected,
        "preconditions": {"source_fingerprint": fingerprint, "proof_status": status, "expected_paid_before": calc["paid"],
                          "expected_due": calc["due"]},
        "required_permission": perm, "run_id": run_id,
        "idempotency_key": "IDK-" + sha([index.case["case_id"], typ, amount, fingerprint])[:16],
        "simulated": True,
    }


AMOUNT_RE = re.compile(r"\$?(\d[\d,]*\.\d{2})")


def final_validator(index, plans, status, calc, bundle_claims, narrative_claims, action, derived_amounts=()):
    """derived_amounts: values computed by deterministic code outside calc steps (e.g. claimant premise)."""
    errors, unsupported = [], []
    known_ids = set(index.records) | {pv["id"] for pv in plans["versions"]} | set(plans["clauses"])
    known_amounts = set()
    for s in calc["steps"]:
        for m in AMOUNT_RE.findall(str(s["value"]) + " " + s["formula"]):
            known_amounts.add(D(m.replace(",", "")))
    for r in index.records.values():
        for k in ("amount", "tcv", "new_tcv", "claimed_shortfall"):
            if r.get(k):
                known_amounts.add(D(r[k]))
    known_amounts |= {D(a) for a in derived_amounts if a is not None}
    for c in ([calc.get("due"), calc.get("paid"), calc.get("delta")]):
        if c is not None:
            known_amounts.add(abs(D(c)))
    accepted = []
    for c in narrative_claims:
        bad_cite = [x for x in c["cites"] if x not in known_ids]
        amounts = [D(a.replace(",", "")) for a in AMOUNT_RE.findall(c["text"])]
        bad_amt = [a for a in amounts if a not in known_amounts and -a not in known_amounts]
        if not c["cites"] or bad_cite or bad_amt:
            unsupported.append({**c, "reason": "no citation" if not c["cites"] else
                                f"unknown ids {bad_cite}" if bad_cite else f"unverifiable amounts {[str(a) for a in bad_amt]}"})
        else:
            accepted.append(c)
    for bc in bundle_claims:
        if not bc["supporting"]:
            errors.append(f"claim {bc['id']} has no supporting evidence")
        if any(x not in known_ids for x in bc["supporting"] + bc["contradicting"]):
            errors.append(f"claim {bc['id']} cites unknown records")
        if status != "VERIFIED" and bc["status"] == "VERIFIED" and bc["id"] == "CLM-DUE":
            errors.append("unverified payout presented as VERIFIED")
    if action["type"] not in ACTION_TYPES:
        errors.append(f"action {action['type']} not in allowlist")
    if action["type"] == "PREPARE_PAYROLL_ADJUSTMENT":
        if status != "VERIFIED":
            errors.append("payroll adjustment proposed without VERIFIED proof")
        if D(action["amount"]) != D(calc["delta"]) or D(action["amount"]) <= 0:
            errors.append("adjustment amount does not equal verified positive variance")
    return {"passed": not errors, "errors": errors, "unsupported_claims": unsupported, "accepted_narrative": accepted}


# --------------------------------------------------------------------------- orchestration

def investigate(case: dict, plans: dict, ledger: list | None = None, model: ModelClient | None = None) -> dict:
    t0 = time.monotonic()
    model = model or ModelClient()
    index = EvidenceIndex(case)
    d = case["dispute"]
    fingerprint = source_fingerprint(case)
    run_id = "RUN-" + sha([fingerprint, ENGINE_VERSION, ledger or []])[:12]
    emp = index.get(d["employee_id"])
    identity = resolve_identity(emp, index.of_type("crm_user"))

    calc = compute(index, plans, identity, Scenario(ledger=ledger or []))
    cutoff = _step(calc, "cutoff")["value"]
    tl = timeline(index, cutoff)
    cfs = replay(index, plans, identity, calc)
    cfs, meterless_meta = rank_scenarios(case["case_id"], cfs)

    hypo = investigator(index, calc, identity)
    sk = skeptic(index, calc, identity, cfs, tl)
    ver = policy_verifier(index, plans, identity, calc, ledger or [])
    status = ver["proof_status"]
    verdict = verdict_for(status, calc, d["claimed_shortfall"])
    action = resolution_planner(index, plans, status, verdict, calc, fingerprint, run_id, sk["findings"])
    bundle = build_bundle(index, plans, calc, identity, ver, verdict, sk, status, d)

    # Model narration (bounded, optional, validated)
    facts = {"due": calc["due"], "paid": calc["paid"], "delta": calc["delta"], "status": status, "verdict": verdict,
             "steps": [{k: s[k] for k in ("label", "value", "rule", "cites")} for s in calc["steps"]]}
    narrative, m1 = model.narrate("explain_resolution", facts, hypo["claims"])
    strongest = next((f for f in sk["findings"] if f["id"] == sk["strongest"]), None)
    sk_claims = [{"text": f"{strongest['title']}. {strongest['detail']}", "cites": strongest["cites"]}] if strongest else []
    sk_text, m2 = model.narrate("strongest_counterargument",
                                {"findings": [{k: f[k] for k in ("title", "detail", "cites", "impact")} for f in sk["findings"]]},
                                sk_claims)
    validation = final_validator(index, plans, status, calc, bundle, narrative + sk_text, action, [hypo["premise"]])
    if not validation["passed"]:
        action = {**action, "type": "REQUEST_EVIDENCE", "amount": None, "blocked_by_validator": validation["errors"]}

    flags = {}
    for f in sk["findings"]:
        if f["severity"] != "high" and f["outcome"] != "UNRESOLVED":
            continue
        for c in f["cites"]:
            flags.setdefault(c, []).append(f["outcome"])
    used = {c for s in calc["steps"] for c in s["cites"]}
    graph = build_graph(index, identity, flags, used)

    core = {"case_id": case["case_id"], "run_id": run_id, "engine_version": ENGINE_VERSION,
            "plan_version": calc.get("plan_version"), "source_fingerprint": fingerprint,
            "proof_status": status, "verdict": verdict, "calculation": calc, "counterfactuals": cfs,
            "bundle": bundle, "proposed_action": action, "identity": identity}
    proof_hash = sha(core)
    return {
        **core, "proof_hash": proof_hash, "title": case["title"], "tags": case.get("tags", []), "dispute": d,
        "timeline": tl, "graph": graph, "hypothesis": hypo, "skeptic": sk, "verification": ver,
        "narrative": validation["accepted_narrative"], "validation": validation,
        "sources_meta": {"provenance": case.get("provenance", {k: "local-fixtures" for k in case["sources"]}),
                         "feeds": case["feeds"], "late_events": case.get("late_events", [])},
        "telemetry": {"latency_ms": round((time.monotonic() - t0) * 1000, 2), "model_calls": model.calls,
                      "model_identity": model.identity, "meterless": meterless_meta},
    }


def build_bundle(index, plans, calc, identity, ver, verdict, sk, status, d):
    claims = []
    supp = sorted({c for s in calc["steps"] for c in s["cites"]})
    contra = sorted({e["id"] for s in calc["steps"] for e in s["excluded"]} |
                    {c for x in ver["conflicts"] for c in x["cites"]})
    open_q = [b["detail"] for b in calc["blockers"]] + [c["detail"] for c in ver["conflicts"] if c["material"]]
    assumptions = ["Value date governs timing (P-4.2)", "Source snapshots are complete for the listed feeds",
                   "Payroll batches with status POSTED were paid"]
    rules = sorted({s["rule"] for s in calc["steps"]})
    claims.append({"id": "CLM-IDENTITY", "statement": f"{identity['employee_id']} is CRM user {identity['crm_user_id']}"
                   if identity["crm_user_id"] else f"{identity['employee_id']} has no unique CRM identity",
                   "status": "VERIFIED" if identity["status"] == "RESOLVED" else "NEEDS_EVIDENCE",
                   "supporting": [identity["employee_id"]] + [c["crm_user_id"] for c in identity["candidates"] if c["strength"] == "STRONG"],
                   "contradicting": [c["crm_user_id"] for c in identity["candidates"] if c["strength"] != "STRONG"],
                   "policy": ["P-2.1"], "calculation": [], "assumptions": ["HRIS email and recorded aliases are authoritative"],
                   "open_questions": [] if identity["status"] == "RESOLVED" else ["Which CRM user is the claimant?"]})
    claims.append({"id": "CLM-DUE", "statement": f"Commission due is {_money(calc['due'])}" if status == "VERIFIED"
                   else "Commission due cannot be established from current evidence",
                   "status": status, "supporting": supp or [d["id"]], "contradicting": contra, "policy": rules,
                   "plan_version": calc.get("plan_version"),
                   "calculation": [{k: s[k] for k in ("key", "label", "value", "formula")} for s in calc["steps"]],
                   "assumptions": assumptions, "open_questions": open_q})
    paid = _step(calc, "paid")
    dup = [c for f in sk["findings"] if f["id"].startswith("SK-DUP") for c in f["cites"]]
    claims.append({"id": "CLM-PAID", "statement": f"Commission paid to date is {_money(calc['paid'])}",
                   "status": "VERIFIED", "supporting": paid["cites"] or [d["id"]], "contradicting": sorted(set(dup)),
                   "policy": ["PAYROLL"], "calculation": [{"key": "paid", "value": paid["value"], "formula": paid["formula"]}],
                   "assumptions": [], "open_questions": [f"Duplicate payroll lines: {', '.join(sorted(set(dup)))}"] if dup else []})
    vstatus = {"SUPPORTED": "VERIFIED", "PARTIALLY_SUPPORTED": "VERIFIED", "REJECTED": "REJECTED"}.get(verdict, status)
    claims.append({"id": "CLM-CLAIM", "statement": f"Claimed shortfall of {_money(d['claimed_shortfall'])} is {verdict.replace('_', ' ').lower()}"
                   + (f" (verified variance {_money(calc['delta'])})" if status == "VERIFIED" else ""),
                   "status": vstatus, "supporting": [d["id"]] + (supp if status == "VERIFIED" else []), "contradicting": contra,
                   "policy": rules, "calculation": [{"key": "delta", "value": calc["delta"]}], "assumptions": [],
                   "open_questions": open_q})
    return claims
