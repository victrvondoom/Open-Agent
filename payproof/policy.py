"""Deterministic commission policy engine (PLAN-AE-2026).

This is the only code that calculates money. It is pure: same inputs + same
scenario -> identical output. Every step records the rule applied, the records
it used (cites), the records it excluded and why, and the intermediate value.

A `scenario` describes a hypothetical replay (counterfactual). Hypothetical
records are always marked `hypothetical: true` and never written back to sources.
"""

import copy
from dataclasses import dataclass, field

from .money import D, fmt, cents


@dataclass
class Scenario:
    id: str = "actual"
    exclude: set = field(default_factory=set)
    add: list = field(default_factory=list)          # [(system, record)] hypothetical records
    patch: dict = field(default_factory=dict)        # {record_id: {field: value}}
    timing_basis: str = "value_date"                 # or "recorded_at" (P-4.2 alternative)
    choose: dict = field(default_factory=dict)       # {conflict_key: record_id}
    split_override: dict | None = None               # {crm_user_id: pct}
    ledger: list = field(default_factory=list)       # simulated payroll lines from executed actions


class View:
    """Scenario-adjusted read-only view over the evidence index."""

    def __init__(self, index, scenario: Scenario):
        self.index, self.s = index, scenario
        self.hyp_ids = {r["id"] for _, r in scenario.add}

    def of_type(self, rtype):
        out = []
        for r in self.index.of_type(rtype):
            if r["id"] in self.s.exclude:
                continue
            if r["id"] in self.s.patch:
                r = {**copy.deepcopy(r), **self.s.patch[r["id"]], "hypothetical": True}
            out.append(r)
        out += [copy.deepcopy(r) for _, r in self.s.add if r.get("type") == rtype]
        if rtype == "payroll_line":
            out += [copy.deepcopy(r) for r in self.s.ledger]
        return out


def _date(rec, field_name, basis="value_date"):
    if basis == "recorded_at" and rec.get("recorded_at"):
        return rec["recorded_at"][:10]
    return rec[field_name][:10]


class Blocked(Exception):
    pass


def compute(index, plans: dict, identity: dict, scenario: Scenario | None = None) -> dict:
    s = scenario or Scenario()
    v = View(index, s)
    case = index.case
    dispute = case["dispute"]
    steps, conflicts, blockers = [], [], []

    def step(key, label, rule, value, cites, formula="", excluded=None, **extra):
        steps.append({"key": key, "label": label, "rule": rule, "value": value, "formula": formula,
                      "cites": [c for c in cites if c], "excluded": excluded or [], **extra})

    cal = next((r for r in v.of_type("pay_calendar") if r["period"] == dispute["period"]), None)
    if cal is None:
        blockers.append({"code": "MISSING_PAY_CALENDAR", "detail": f"No payroll calendar for {dispute['period']}; cutoff unknown",
                         "cites": [dispute["id"]]})
        step("cutoff", "Measurement cutoff", "PAYCAL", "unknown", [])
        paid, pl_cites = _paid(v, dispute)
        step("paid", "Commission already paid", "PAYROLL", fmt(paid), pl_cites, formula="sum(posted payroll lines)")
        return _result(s, steps, conflicts, blockers, None, paid)
    cutoff = cal["measurement_cutoff"]
    step("cutoff", "Measurement cutoff", "PAYCAL", cutoff, [cal["id"]])

    opp = next((r for r in v.of_type("opportunity") if r["id"] == dispute["opportunity_id"]), None)
    if opp is None:
        blockers.append({"code": "MISSING_OPPORTUNITY", "detail": "Disputed opportunity not found in CRM", "cites": [dispute["id"]]})
        return _result(s, steps, conflicts, blockers, None, None)

    # P-7.1 eligibility
    if opp["stage"] != "closed_won":
        step("eligibility", "Opportunity stage", "P-7.1", "0.00", [opp["id"]],
             formula=f"stage={opp['stage']} is not closed_won -> nothing commissionable")
        paid, pl_cites = _paid(v, dispute)
        step("paid", "Commission already paid", "PAYROLL", fmt(paid), pl_cites, formula="sum(posted payroll lines)")
        return _result(s, steps, conflicts, blockers, D(0), paid, eligible=False)
    step("eligibility", "Opportunity stage", "P-7.1", "closed_won", [opp["id"]])

    # Identity
    if identity["status"] != "RESOLVED":
        blockers.append({"code": "IDENTITY_UNRESOLVED",
                         "detail": f"Employee {identity['employee_id']} cannot be linked to exactly one CRM user ({identity['status']})",
                         "cites": [identity["employee_id"]] + [c["crm_user_id"] for c in identity["candidates"]]})
    crm_user = identity["crm_user_id"]

    # P-2.1 split credit
    splits = [r for r in v.of_type("split") if r["opportunity_id"] == opp["id"]]
    if s.split_override is not None:
        splits = [{"id": f"HYP-SPL-{u}", "crm_user_id": u, "pct": p, "hypothetical": True} for u, p in s.split_override.items()]
    total = sum((D(x["pct"]) for x in splits), D(0))
    mine = [x for x in splits if x["crm_user_id"] == crm_user] if crm_user else []
    pct = sum((D(x["pct"]) for x in mine), D(0))
    if total != D(100):
        conflicts.append({"key": "split_total", "code": "SPLIT_TOTAL_INVALID", "material": True,
                          "detail": f"Splits on {opp['id']} total {total}%, policy requires 100%",
                          "cites": [x["id"] for x in splits]})
    step("split", "Claimant split credit", "P-2.1", f"{pct}%", [x["id"] for x in splits],
         formula=f"split for {crm_user or '?'} = {pct}% (all splits total {total}%)", pct=str(pct))

    # P-3.1 eligible value
    contracts = [r for r in v.of_type("contract") if r["opportunity_id"] == opp["id"]]
    if not contracts:
        blockers.append({"code": "MISSING_CONTRACT", "detail": f"No signed contract found for {opp['id']} in CLM",
                         "cites": [opp["id"]]})
        eligible = None
    else:
        contract = contracts[0]
        amends = [r for r in v.of_type("amendment") if r["contract_id"] == contract["id"]]
        applied = [a for a in amends if _date(a, "signed_date", s.timing_basis) <= cutoff]
        excluded = [{"id": a["id"], "reason": f"signed {a['signed_date']} after cutoff {cutoff}"}
                    for a in amends if a not in applied]
        eligible = D(contract["tcv"])
        cites = [contract["id"]]
        formula = f"contract TCV {fmt(eligible)}"
        if applied:
            latest = max(a["effective_date"] for a in applied)
            top = [a for a in applied if a["effective_date"] == latest]
            values = {D(a["new_tcv"]) for a in top}
            chosen = top[0]
            if len(top) > 1:
                pick = s.choose.get("amendment")
                chosen = next((a for a in top if a["id"] == pick), top[0])
                if len(values) > 1:
                    conflicts.append({"key": "amendment", "code": "AMENDMENT_CONFLICT", "material": None,
                                      "detail": f"{len(top)} amendments share effective date {latest} with different values",
                                      "options": [a["id"] for a in top], "cites": [a["id"] for a in top]})
            eligible = D(chosen["new_tcv"])
            cites += [a["id"] for a in top]
            formula = f"amendment {chosen['id']} (effective {latest}) sets eligible value {fmt(eligible)}"
        step("eligible", "Eligible contract value", "P-3.1", fmt(eligible), cites, formula=formula, excluded=excluded)

    # P-3.2 net collected
    if case["feeds"].get("billing.payments") != "ok":
        blockers.append({"code": "PAYMENTS_FEED_UNAVAILABLE", "detail": "Billing payments feed did not return data; collection cannot be established",
                         "cites": []})
        net = None
    else:
        invoices = {r["id"]: r for r in v.of_type("invoice") if r.get("opportunity_id") == opp["id"]}
        inc, exc = [], []
        pay_sum = D(0)
        for p in v.of_type("payment"):
            if p["invoice_id"] not in invoices:
                continue
            d = _date(p, "value_date", s.timing_basis)
            if d <= cutoff:
                pay_sum += D(p["amount"]); inc.append(p["id"])
            else:
                exc.append({"id": p["id"], "reason": f"{'recorded' if s.timing_basis == 'recorded_at' else 'value date'} {d} after cutoff"})
        ref_sum = D(0)
        for r in v.of_type("refund"):
            if r["invoice_id"] in invoices:
                if _date(r, "value_date", s.timing_basis) <= cutoff:
                    ref_sum += D(r["amount"]); inc.append(r["id"])
                else:
                    exc.append({"id": r["id"], "reason": "refund after cutoff"})
        cn_sum = D(0)
        for c in v.of_type("credit_note"):
            if c["invoice_id"] in invoices:
                d = _date(c, "issued_date", s.timing_basis)
                if d <= cutoff:
                    cn_sum += D(c["amount"]); inc.append(c["id"])
                else:
                    exc.append({"id": c["id"], "reason": f"issued {d} after cutoff"})
        net = pay_sum - ref_sum - cn_sum
        step("collected", "Net cash collected by cutoff", "P-3.2", fmt(net), list(invoices) + inc,
             formula=f"payments {fmt(pay_sum)} - refunds {fmt(ref_sum)} - credit notes {fmt(cn_sum)}", excluded=exc)

    # P-3.2 base
    base = None
    if eligible is not None and net is not None:
        base = max(D(0), min(eligible, net))
        step("base", "Commissionable base", "P-3.2", fmt(base), [],
             formula=f"max(0, min(eligible {fmt(eligible)}, collected {fmt(net)}))")

    # P-4.1 / P-5.1 rate
    version = next((pv for pv in plans["versions"] if pv["effective_from"] <= opp["close_date"] <= pv["effective_to"]), None)
    rate = D(version["rate"])
    rate_cites, rate_formula, rate_excl = [version["id"], opp["id"]], f"{version['id']} rate {version['rate']} (close {opp['close_date']})", []
    for e in v.of_type("policy_exception"):
        if e["opportunity_id"] != opp["id"]:
            continue
        if e["status"] == "APPROVED" and e.get("approval_ref"):
            rate = D(e["rate_override"]); rate_cites.append(e["id"])
            rate_formula += f"; approved exception {e['id']} ({e['approval_ref']}) overrides to {e['rate_override']}"
        else:
            rate_excl.append({"id": e["id"], "reason": f"exception status {e['status']} without approval reference (P-5.1)"})
    step("rate", "Commission rate", "P-4.1/P-5.1", str(rate), rate_cites, formula=rate_formula, excluded=rate_excl,
         plan_version=version["id"])

    due = None
    if base is not None:
        due = cents(base * pct / D(100) * rate)
        step("due", "Commission due", "P-6.1", fmt(due), [],
             formula=f"{fmt(base)} x {pct}% x {rate} = {fmt(due)} (ROUND_HALF_UP once)")

    paid, pl_cites = _paid(v, dispute)
    step("paid", "Commission already paid", "PAYROLL", fmt(paid), pl_cites, formula="sum(lines in POSTED batches)")
    return _result(s, steps, conflicts, blockers, due, paid, plan_version=version["id"])


def _paid(v, dispute):
    posted = {b["id"] for b in v.of_type("payroll_batch") if b["status"] == "POSTED"} | {"PB-SIM-ADJ"}
    lines = [l for l in v.of_type("payroll_line") if l["employee_id"] == dispute["employee_id"]
             and l["opportunity_id"] == dispute["opportunity_id"] and l["batch_id"] in posted]
    return sum((D(l["amount"]) for l in lines), D(0)), [l["id"] for l in lines]


def _result(s, steps, conflicts, blockers, due, paid, **extra):
    delta = (due - paid) if (due is not None and paid is not None) else None
    if delta is not None:
        steps.append({"key": "delta", "label": "Variance (due - paid)", "rule": "P-6.1", "value": fmt(delta),
                      "formula": f"{fmt(due)} - {fmt(paid)}", "cites": [], "excluded": []})
    return {"scenario": s.id, "steps": steps, "conflicts": conflicts, "blockers": blockers,
            "due": fmt(due) if due is not None else None, "paid": fmt(paid) if paid is not None else None,
            "delta": fmt(delta) if delta is not None else None, **extra}
