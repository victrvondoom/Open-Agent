"""Build a dispute case (six synthetic source-system snapshots) from a compact spec.

Shared by the fixture generator (scripts/build_fixtures.py) and runtime dispute intake
(payproof/intake.py), so benchmark cases and user-filed cases go through identical code.
"""


def ts(date, hour="10:00:00"):
    return f"{date}T{hour}Z"


def build(spec):
    cutoff = spec.get("cutoff", "2026-06-30")
    period = spec.get("period", "2026-Q2")
    emp = spec["claimant"]
    hris = [{
        "id": emp["id"], "type": "employee", "name": emp["name"], "email": emp["email"],
        "alt_emails": emp.get("alt_emails", []), "territory": emp.get("territory", "WEST"),
        "effective_at": "2025-01-06", "recorded_at": ts("2025-01-06"),
    }]
    crm = []
    for u in spec["crm_users"]:
        crm.append({"id": u["id"], "type": "crm_user", "name": u["name"], "email": u["email"],
                    "effective_at": "2025-01-06", "recorded_at": ts("2025-01-06")})
    o = spec["opp"]
    crm.append({"id": o["id"], "type": "opportunity", "account": o["account"], "amount": o["amount"],
                "stage": o.get("stage", "closed_won"), "close_date": o["close_date"], "owner": o["owner"],
                "effective_at": o["close_date"], "recorded_at": ts(o["close_date"], "17:00:00")})
    for i, (user, pct) in enumerate(o.get("splits", [(o["owner"], "100")]), 1):
        crm.append({"id": f"SPL-{o['id'][4:]}-{i}", "type": "split", "opportunity_id": o["id"],
                    "crm_user_id": user, "pct": pct,
                    "effective_at": o["close_date"], "recorded_at": ts(o["close_date"], "17:05:00")})
    clm = []
    c = spec.get("contract")
    if c:
        clm.append({"id": c["id"], "type": "contract", "opportunity_id": o["id"], "tcv": c["tcv"],
                    "signed_date": c["signed"], "effective_at": c["signed"], "recorded_at": ts(c["signed"], "18:00:00")})
        for a in spec.get("amendments", []):
            clm.append({"id": a["id"], "type": "amendment", "contract_id": c["id"], "new_tcv": a["new_tcv"],
                        "effective_date": a["effective"], "signed_date": a["signed"],
                        "effective_at": a["effective"], "recorded_at": ts(a["signed"], "18:00:00")})
    billing = []
    for inv in spec.get("invoices", []):
        billing.append({"id": inv["id"], "type": "invoice", "contract_id": c["id"] if c else None,
                        "opportunity_id": o["id"], "amount": inv["amount"], "issued_date": inv["issued"],
                        "effective_at": inv["issued"], "recorded_at": ts(inv["issued"])})
    for p in spec.get("payments", []):
        billing.append({"id": p["id"], "type": "payment", "invoice_id": p["inv"], "amount": p["amount"],
                        "value_date": p["value"], "effective_at": p["value"],
                        "recorded_at": ts(p.get("recorded", p["value"]), "12:00:00")})
    for cn in spec.get("credit_notes", []):
        billing.append({"id": cn["id"], "type": "credit_note", "invoice_id": cn["inv"], "amount": cn["amount"],
                        "issued_date": cn["issued"], "reason": cn.get("reason", "service credit"),
                        "effective_at": cn["issued"], "recorded_at": ts(cn["issued"], "13:00:00")})
    for r in spec.get("refunds", []):
        billing.append({"id": r["id"], "type": "refund", "invoice_id": r["inv"], "amount": r["amount"],
                        "value_date": r["value"], "effective_at": r["value"], "recorded_at": ts(r["value"], "14:00:00")})
    comp = []
    for e in spec.get("exceptions", []):
        comp.append({"id": e["id"], "type": "policy_exception", "opportunity_id": o["id"], "employee_id": emp["id"],
                     "rate_override": e["rate"], "status": e["status"], "approval_ref": e.get("approval_ref"),
                     "approved_by": e.get("approved_by"), "justification": e.get("why", "strategic logo"),
                     "effective_at": e.get("date", o["close_date"]), "recorded_at": ts(e.get("date", o["close_date"]))})
    payroll = [{"id": f"CAL-{period}", "type": "pay_calendar", "period": period, "measurement_cutoff": cutoff,
                "effective_at": cutoff, "recorded_at": ts("2026-01-02")}]
    batches = {}
    for ln in spec.get("payroll", []):
        b = ln["batch"]
        if b not in batches:
            batches[b] = {"id": b, "type": "payroll_batch", "status": ln.get("batch_status", "POSTED"),
                          "posted_date": ln["posted"], "approved_by": "PAYROLL-OPS-2",
                          "effective_at": ln["posted"], "recorded_at": ts(ln["posted"], "20:00:00")}
        payroll.append({"id": ln["id"], "type": "payroll_line", "batch_id": b, "employee_id": emp["id"],
                        "opportunity_id": o["id"], "line_type": ln["type"], "amount": ln["amount"],
                        "reference_id": ln.get("ref", o["id"]), "memo": ln.get("memo", ""),
                        "effective_at": ln["posted"], "recorded_at": ts(ln["posted"], "20:00:00")})
    payroll[1:1] = list(batches.values())
    feeds = {"hris": "ok", "crm": "ok", "clm": "ok", "billing": "ok", "billing.payments": spec.get("payments_feed", "ok"),
             "comp": "ok", "payroll": "ok"}
    return {
        "case_id": spec["case_id"],
        "title": spec["title"],
        "tags": spec.get("tags", []),
        "dispute": {
            "id": "DSP-" + spec["case_id"][5:], "employee_id": emp["id"], "opportunity_id": o["id"],
            "claimed_shortfall": spec["claim"], "filed_at": spec.get("filed", "2026-07-08"),
            "period": period, "narrative": spec["narrative"],
            "effective_at": spec.get("filed", "2026-07-08"), "recorded_at": ts(spec.get("filed", "2026-07-08")),
        },
        "feeds": feeds,
        "sources": {
            "hris": {"system": "hris-sim (Workday-like)", "records": hris},
            "crm": {"system": "crm-sim (Salesforce-like)", "records": crm},
            "clm": {"system": "clm-sim (contract lifecycle)", "records": clm},
            "billing": {"system": "billing-sim (NetSuite-like)", "records": billing},
            "comp": {"system": "comp-admin-sim", "records": comp},
            "payroll": {"system": "payroll-sim (ADP-like)", "records": payroll},
        },
    }
