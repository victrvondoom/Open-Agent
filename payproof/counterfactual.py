"""Counterfactual payout replay.

Each scenario is a hypothetical change to the evidence, replayed through the same
deterministic policy engine. Results are labelled HYPOTHETICAL and never
written back to source systems or treated as financial events.
"""

from .money import D, fmt
from .policy import Scenario, compute


def _delta(a, b):
    if a is None or b is None:
        return None
    return fmt(D(a) - D(b))


def generate_scenarios(index, actual: dict, identity: dict) -> list[tuple[Scenario, dict]]:
    """Derive scenarios from the facts actually present in this case."""
    case = index.case
    d = case["dispute"]
    cutoff = next(s["value"] for s in actual["steps"] if s["key"] == "cutoff")
    out = []

    def add(sid, title, question, changed, **kw):
        out.append((Scenario(id=sid, **kw), {"id": sid, "title": title, "question": question, "changed_facts": changed}))

    invoices = [r for r in index.of_type("invoice") if r.get("opportunity_id") == d["opportunity_id"]]
    inv_ids = {i["id"] for i in invoices}
    payments = [p for p in index.of_type("payment") if p["invoice_id"] in inv_ids]

    # Late-arriving payments: value date before cutoff, recorded after
    late = [p for p in payments if p["value_date"] <= cutoff < p["recorded_at"][:10]]
    if late:
        add("cf_recorded_timing", "Use system-recorded dates instead of value dates",
            "What if timing followed when payments were recorded rather than their value date (alternative to P-4.2)?",
            [p["id"] for p in late], timing_basis="recorded_at")

    # Full payment of outstanding invoices
    for inv in invoices:
        paid = sum((D(p["amount"]) for p in payments if p["invoice_id"] == inv["id"] and p["value_date"] <= cutoff), D(0))
        gap = D(inv["amount"]) - paid
        if gap > 0 and case["feeds"].get("billing.payments") == "ok":
            add(f"cf_full_payment_{inv['id']}", f"Invoice {inv['id']} paid in full before cutoff",
                f"What if the outstanding {fmt(gap)} on {inv['id']} had been collected by {cutoff}?", [inv["id"]],
                add=[("billing", {"id": f"HYP-PAY-{inv['id']}", "type": "payment", "invoice_id": inv["id"], "amount": str(gap),
                                  "value_date": cutoff, "recorded_at": cutoff + "T00:00:00Z", "hypothetical": True})])

    # Credit notes moved across the cutoff
    for cn in index.of_type("credit_note"):
        if cn["invoice_id"] not in inv_ids:
            continue
        if cn["issued_date"] <= cutoff:
            add(f"cf_cn_after_{cn['id']}", f"Credit note {cn['id']} issued after cutoff",
                f"What if {cn['id']} ({fmt(D(cn['amount']))}) had been issued after the {cutoff} cutoff?", [cn["id"]],
                patch={cn["id"]: {"issued_date": "2099-01-01", "recorded_at": "2099-01-01T00:00:00Z"}})
        else:
            add(f"cf_cn_before_{cn['id']}", f"Credit note {cn['id']} issued before cutoff",
                f"What if {cn['id']} had been issued on or before {cutoff}?", [cn["id"]],
                patch={cn["id"]: {"issued_date": cutoff, "recorded_at": cutoff + "T00:00:00Z"}})

    # Amendments
    for a in index.of_type("amendment"):
        if a["signed_date"] <= cutoff:
            add(f"cf_no_amend_{a['id']}", f"Amendment {a['id']} not applied",
                f"What if {a['id']} were void and the original contract value governed?", [a["id"]], exclude={a["id"]})
        else:
            add(f"cf_amend_signed_{a['id']}", f"Amendment {a['id']} signed before cutoff",
                f"What if {a['id']} (signed {a['signed_date']}) had been signed by {cutoff}?", [a["id"]],
                patch={a["id"]: {"signed_date": cutoff, "recorded_at": cutoff + "T00:00:00Z"}})
    for c in actual["conflicts"]:
        if c["key"] == "amendment":
            for opt in c["options"]:
                add(f"cf_choose_{opt}", f"Conflict resolved in favour of {opt}",
                    f"What if {opt} is the governing amendment?", c["options"], choose={"amendment": opt})

    # Split attribution
    me = identity.get("crm_user_id")
    splits = [s for s in index.of_type("split") if s["opportunity_id"] == d["opportunity_id"]]
    others = [u["id"] for u in index.of_type("crm_user") if u["id"] != me]
    if me and len(splits) == 1 and others:
        add("cf_split_5050", f"Territory split misattributed (50/50 with {others[0]})",
            f"What if half the credit belonged to {others[0]}?", [splits[0]["id"]], split_override={me: "50", others[0]: "50"})
    elif me and len(splits) > 1:
        add("cf_split_full", "Full credit to claimant", "What if the claimant held 100% of the split?",
            [s["id"] for s in splits], split_override={me: "100"})

    # Payroll duplicates
    lines = [l for l in index.of_type("payroll_line") if l["employee_id"] == d["employee_id"] and l["opportunity_id"] == d["opportunity_id"]]
    seen = {}
    for l in lines:
        key = (l["line_type"], l["reference_id"], l["amount"])
        if key in seen:
            add(f"cf_dedupe_{l['id']}", f"Duplicate payroll line {l['id']} removed",
                f"What if {l['id']} (duplicate of {seen[key]}) had never been posted?", [l["id"], seen[key]], exclude={l["id"]})
        else:
            seen[key] = l["id"]

    # Pending exceptions
    for e in index.of_type("policy_exception"):
        if e["status"] != "APPROVED":
            add(f"cf_exc_{e['id']}", f"Exception {e['id']} approved",
                f"What if {e['id']} (rate {e['rate_override']}) had been approved?", [e["id"]],
                patch={e["id"]: {"status": "APPROVED", "approval_ref": "HYPOTHETICAL"}})
    return out


def replay(index, plans, identity, actual: dict) -> list[dict]:
    results = []
    for scenario, meta in generate_scenarios(index, actual, identity):
        r = compute(index, plans, identity, scenario)
        results.append({**meta, "hypothetical": True, "due": r["due"], "paid": r["paid"], "delta": r["delta"],
                        "due_change": _delta(r["due"], actual["due"]), "paid_change": _delta(r["paid"], actual["paid"]),
                        "delta_change": _delta(r["delta"], actual["delta"]),
                        "blocked": bool(r["blockers"]),
                        "steps_changed": [s["key"] for s in r["steps"]
                                          if s["value"] != next((a["value"] for a in actual["steps"] if a["key"] == s["key"]), None)]})

    def impact(x):
        return abs(D(x["delta_change"])) if x["delta_change"] else D(0)

    results.sort(key=lambda x: (-impact(x), x["id"]))
    return results
