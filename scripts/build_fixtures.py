"""Generate synthetic source-system snapshots for every dispute case.

All people, companies and amounts are fictional. Output: data/cases/<CASE-ID>.json.
Ground truth lives separately in bench/ground_truth.json and was computed by hand.

Run: python3 scripts/build_fixtures.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "cases"


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


def std(case_id, title, emp_id, name, amount, close="2026-03-20", **kw):
    """Common shape: one rep, one opportunity, contract == CRM amount, one invoice."""
    user = "U-" + emp_id[2:]
    email = name.lower().replace(" ", ".") + "@peoplepay.example"
    spec = {
        "case_id": case_id, "title": title,
        "claimant": {"id": emp_id, "name": name, "email": email},
        "crm_users": [{"id": user, "name": name, "email": email}],
        "opp": {"id": "OPP-" + case_id[5:], "account": kw.pop("account", "Synthetic Account"), "amount": amount,
                "close_date": close, "owner": user},
        "contract": {"id": "CTR-" + case_id[5:], "tcv": amount, "signed": close},
        "invoices": [{"id": "INV-" + case_id[5:], "amount": amount, "issued": "2026-04-01"}],
        "payments": [{"id": "PAY-" + case_id[5:] + "-1", "inv": "INV-" + case_id[5:], "amount": amount, "value": "2026-04-28"}],
    }
    for k, v in kw.items():
        if k == "opp":
            spec["opp"].update(v)
        else:
            spec[k] = v
    return spec


def specs():
    S = []
    # ---- Demo case: the full story -------------------------------------------------
    S.append({
        "case_id": "CASE-1001",
        "title": "Northwind Logistics — $3,000 shortfall claim",
        "tags": ["demo", "amendment", "partial_payment", "credit_note", "late_arriving", "duplicate_adjustment", "identity_alias"],
        "claimant": {"id": "E-1042", "name": "Maya Chen", "email": "maya.chen@peoplepay.example", "territory": "WEST"},
        "crm_users": [
            {"id": "U-77", "name": "M. Chen", "email": "maya.chen@peoplepay.example"},
            {"id": "U-91", "name": "Daniel Ortiz", "email": "daniel.ortiz@peoplepay.example"},
        ],
        "opp": {"id": "OPP-5521", "account": "Northwind Logistics", "amount": "60000.00", "close_date": "2026-03-14", "owner": "U-77"},
        "contract": {"id": "CTR-3301", "tcv": "60000.00", "signed": "2026-03-14"},
        "amendments": [{"id": "AMD-3301-1", "new_tcv": "50000.00", "effective": "2026-04-01", "signed": "2026-03-28"}],
        "invoices": [{"id": "INV-8801", "amount": "50000.00", "issued": "2026-04-02"}],
        "payments": [
            {"id": "PAY-44120", "inv": "INV-8801", "amount": "36000.00", "value": "2026-04-20", "recorded": "2026-04-21"},
            {"id": "PAY-44987", "inv": "INV-8801", "amount": "9000.00", "value": "2026-06-10", "recorded": "2026-07-03"},
        ],
        "credit_notes": [{"id": "CN-0077", "inv": "INV-8801", "amount": "2000.00", "issued": "2026-05-15", "reason": "SLA credit"}],
        "payroll": [
            {"id": "PL-20260531-118", "batch": "PB-2026-05", "type": "commission", "amount": "3600.00", "posted": "2026-05-31", "memo": "Q2 commission on collected cash"},
            {"id": "PL-20260630-041", "batch": "PB-2026-06", "type": "clawback", "amount": "-200.00", "ref": "CN-0077", "posted": "2026-06-30", "memo": "Clawback CN-0077"},
            {"id": "PL-20260630-042", "batch": "PB-2026-06", "type": "clawback", "amount": "-200.00", "ref": "CN-0077", "posted": "2026-06-30", "memo": "Clawback CN-0077 (re-import)"},
        ],
        "claim": "3000.00",
        "narrative": "I closed Northwind at $60,000 in March. At 10% I should have earned $6,000 but I've only received around $3,000. Please fix the $3,000 shortfall.",
    })
    S.append(std("CASE-1002", "Correct payout, claim refuted", "E-2002", "Liam Walsh", "40000.00",
                 account="Bluefin Health", claim="500.00", tags=["straightforward"],
                 payroll=[{"id": "PL-1002-1", "batch": "PB-2026-05", "type": "commission", "amount": "4000.00", "posted": "2026-05-31"}],
                 narrative="I think my Bluefin commission is $500 short."))
    S.append(std("CASE-1003", "Simple underpayment", "E-2003", "Aisha Bello", "30000.00",
                 account="Cobalt Freight", claim="1000.00", tags=["underpayment"],
                 payroll=[{"id": "PL-1003-1", "batch": "PB-2026-05", "type": "commission", "amount": "2000.00", "posted": "2026-05-31"}],
                 narrative="Paid $2,000 on a $30,000 fully-paid deal. Should be $3,000."))
    S.append(std("CASE-1004", "Overpayment discovered", "E-2004", "Tomás Rivera", "20000.00",
                 account="Delta Ceramics", claim="300.00", tags=["overpayment"],
                 payroll=[{"id": "PL-1004-1", "batch": "PB-2026-05", "type": "commission", "amount": "2500.00", "posted": "2026-05-31"}],
                 narrative="I believe I am owed another $300 on Delta Ceramics."))
    S.append(std("CASE-1005", "Partial payment explains gap", "E-2005", "Hana Sato", "50000.00",
                 account="Evergreen Labs", claim="2500.00", tags=["partial_payment"],
                 payments=[{"id": "PAY-1005-1", "inv": "INV-1005", "amount": "25000.00", "value": "2026-05-02"}],
                 payroll=[{"id": "PL-1005-1", "batch": "PB-2026-05", "type": "commission", "amount": "2500.00", "posted": "2026-05-31"}],
                 narrative="Deal was $50,000; I was only paid half the commission."))
    S.append(std("CASE-1006", "Credit note before cutoff", "E-2006", "Noah Fischer", "40000.00",
                 account="Fjord Analytics", claim="500.00", tags=["credit_note"],
                 credit_notes=[{"id": "CN-1006", "inv": "INV-1006", "amount": "5000.00", "issued": "2026-05-01"}],
                 payroll=[{"id": "PL-1006-1", "batch": "PB-2026-05", "type": "commission", "amount": "3500.00", "posted": "2026-05-31"}],
                 narrative="My Fjord commission was reduced by $500 without explanation."))
    S.append(std("CASE-1007", "Credit note after cutoff (premature clawback)", "E-2007", "Olivia Grant", "40000.00",
                 account="Granite Systems", claim="500.00", tags=["credit_note", "underpayment"],
                 credit_notes=[{"id": "CN-1007", "inv": "INV-1007", "amount": "5000.00", "issued": "2026-07-15"}],
                 payroll=[{"id": "PL-1007-1", "batch": "PB-2026-06", "type": "commission", "amount": "3500.00", "posted": "2026-06-30"}],
                 narrative="Payroll deducted $500 for a credit that was issued after the quarter closed."))
    S.append(std("CASE-1008", "Split commission underpaid", "E-2008", "Ravi Menon", "80000.00",
                 account="Harbor Retail", claim="800.00", tags=["split", "underpayment"],
                 crm_users=[{"id": "U-2008", "name": "Ravi Menon", "email": "ravi.menon@peoplepay.example"},
                            {"id": "U-3008", "name": "Grace Kim", "email": "grace.kim@peoplepay.example"}],
                 opp={"splits": [("U-2008", "60"), ("U-3008", "40")]},
                 payroll=[{"id": "PL-1008-1", "batch": "PB-2026-05", "type": "commission", "amount": "4000.00", "posted": "2026-05-31"}],
                 narrative="My split on Harbor Retail is 60%, but I was paid as if it were 50%."))
    S.append(std("CASE-1009", "Split assignments exceed 100%", "E-2009", "Sofia Lind", "80000.00",
                 account="Ironwood Bank", claim="1000.00", tags=["split", "contradiction"],
                 crm_users=[{"id": "U-2009", "name": "Sofia Lind", "email": "sofia.lind@peoplepay.example"},
                            {"id": "U-3009", "name": "Ben Okafor", "email": "ben.okafor@peoplepay.example"}],
                 opp={"splits": [("U-2009", "60"), ("U-3009", "50")]},
                 payroll=[{"id": "PL-1009-1", "batch": "PB-2026-05", "type": "commission", "amount": "4000.00", "posted": "2026-05-31"}],
                 narrative="My split is 60% but payroll paid 50%."))
    S.append(std("CASE-1010", "Conflicting amendments (material)", "E-2010", "Marco Bianchi", "60000.00",
                 account="Juniper Media", claim="1000.00", tags=["amendment", "contradiction"],
                 amendments=[{"id": "AMD-1010-A", "new_tcv": "45000.00", "effective": "2026-04-01", "signed": "2026-03-30"},
                             {"id": "AMD-1010-B", "new_tcv": "55000.00", "effective": "2026-04-01", "signed": "2026-03-31"}],
                 invoices=[{"id": "INV-1010", "amount": "50000.00", "issued": "2026-04-02"}],
                 payments=[{"id": "PAY-1010-1", "inv": "INV-1010", "amount": "50000.00", "value": "2026-05-05"}],
                 payroll=[{"id": "PL-1010-1", "batch": "PB-2026-05", "type": "commission", "amount": "4500.00", "posted": "2026-05-31"}],
                 narrative="Contract was amended to $55,000. I should get commission on the full $50,000 collected."))
    S.append(std("CASE-1011", "Conflicting amendments (immaterial)", "E-2011", "Elena Popescu", "80000.00",
                 account="Kestrel Energy", claim="1000.00", tags=["amendment", "contradiction", "underpayment"],
                 amendments=[{"id": "AMD-1011-A", "new_tcv": "70000.00", "effective": "2026-04-01", "signed": "2026-03-30"},
                             {"id": "AMD-1011-B", "new_tcv": "75000.00", "effective": "2026-04-01", "signed": "2026-03-31"}],
                 invoices=[{"id": "INV-1011", "amount": "50000.00", "issued": "2026-04-02"}],
                 payments=[{"id": "PAY-1011-1", "inv": "INV-1011", "amount": "50000.00", "value": "2026-05-05"}],
                 payroll=[{"id": "PL-1011-1", "batch": "PB-2026-05", "type": "commission", "amount": "4000.00", "posted": "2026-05-31"}],
                 narrative="$50,000 has been collected on Kestrel; I was paid on $40,000."))
    S.append(std("CASE-1012", "Backdated amendment signed after cutoff", "E-2012", "Jonas Berg", "60000.00",
                 account="Lumen Robotics", claim="2000.00", tags=["amendment", "late_arriving"],
                 amendments=[{"id": "AMD-1012-1", "new_tcv": "80000.00", "effective": "2026-05-01", "signed": "2026-07-10"}],
                 invoices=[{"id": "INV-1012", "amount": "60000.00", "issued": "2026-04-01"},
                           {"id": "INV-1012-B", "amount": "20000.00", "issued": "2026-07-12"}],
                 payments=[{"id": "PAY-1012-1", "inv": "INV-1012", "amount": "60000.00", "value": "2026-05-20"}],
                 payroll=[{"id": "PL-1012-1", "batch": "PB-2026-05", "type": "commission", "amount": "6000.00", "posted": "2026-05-31"}],
                 narrative="The contract was upsized to $80,000 effective May 1. I'm owed $2,000 more."))
    S.append(std("CASE-1013", "Ambiguous rep identity", "E-2013", "Priya Nair", "45000.00",
                 account="Meridian Foods", claim="4500.00", tags=["identity", "missing_evidence"],
                 crm_users=[{"id": "U-2013", "name": "Priya Nair", "email": "p.nair@acquiredco.example"},
                            {"id": "U-4013", "name": "Priya Nair", "email": "priya.n@partner.example"}],
                 opp={"owner": "U-2013", "splits": [("U-2013", "100")]},
                 narrative="I was never paid for Meridian Foods."))
    S.append(std("CASE-1014", "Identity resolved via HRIS alias", "E-2014", "Kwame Asante", "30000.00",
                 account="Nimbus Travel", claim="3000.00", tags=["identity", "underpayment"],
                 claimant={"id": "E-2014", "name": "Kwame Asante", "email": "kwame.asante@peoplepay.example",
                           "alt_emails": ["k.asante@legacy-crm.example"]},
                 crm_users=[{"id": "U-2014", "name": "K. Asante", "email": "k.asante@legacy-crm.example"}],
                 opp={"owner": "U-2014", "splits": [("U-2014", "100")]},
                 narrative="My Nimbus commission was never paid. The CRM still uses my legacy login."))
    S.append(std("CASE-1015", "Missing contract (negative case)", "E-2015", "Chloe Dubois", "45000.00",
                 account="Orion Mining", claim="4500.00", tags=["missing_evidence", "negative_demo"],
                 contract=None, invoices=[{"id": "INV-1015", "amount": "45000.00", "issued": "2026-04-01"}],
                 payments=[{"id": "PAY-1015-1", "inv": "INV-1015", "amount": "45000.00", "value": "2026-04-28"}],
                 narrative="Orion closed at $45,000 and I received nothing. Please pay $4,500 now."))
    S.append(std("CASE-1016", "Payments feed unavailable", "E-2016", "Felix Wagner", "30000.00",
                 account="Pinnacle Insurance", claim="3000.00", tags=["missing_evidence"],
                 payments=[], payments_feed="unavailable",
                 narrative="Pinnacle has paid; I'm owed $3,000."))
    S.append(std("CASE-1017", "Unpaid invoice, nothing due yet", "E-2017", "Zara Ahmed", "20000.00",
                 account="Quartz Dental", claim="2000.00", tags=["partial_payment"],
                 payments=[],
                 narrative="Quartz signed in March; where is my $2,000?"))
    S.append(std("CASE-1018", "Approved rate exception", "E-2018", "Lucas Moreau", "50000.00",
                 account="Redwood Pharma", claim="1000.00", tags=["exception", "underpayment"],
                 exceptions=[{"id": "EXC-1018", "rate": "0.12", "status": "APPROVED", "approval_ref": "APR-7781", "approved_by": "VP-SALES-1"}],
                 payroll=[{"id": "PL-1018-1", "batch": "PB-2026-05", "type": "commission", "amount": "5000.00", "posted": "2026-05-31"}],
                 narrative="Redwood had an approved 12% strategic-logo rate. I was paid 10%."))
    S.append(std("CASE-1019", "Unapproved rate exception", "E-2019", "Mia Novak", "50000.00",
                 account="Sable Security", claim="1000.00", tags=["exception"],
                 exceptions=[{"id": "EXC-1019", "rate": "0.12", "status": "PENDING"}],
                 payroll=[{"id": "PL-1019-1", "batch": "PB-2026-05", "type": "commission", "amount": "5000.00", "posted": "2026-05-31"}],
                 narrative="My manager promised 12% on Sable."))
    S.append(std("CASE-1020", "Plan version boundary (overpaid)", "E-2020", "Ethan Cole", "50000.00",
                 close="2026-07-02", account="Tidal Water", claim="200.00", tags=["policy_version", "overpayment"],
                 cutoff="2026-09-30", period="2026-Q3", filed="2026-10-05",
                 invoices=[{"id": "INV-1020", "amount": "50000.00", "issued": "2026-07-05"}],
                 payments=[{"id": "PAY-1020-1", "inv": "INV-1020", "amount": "50000.00", "value": "2026-08-15"}],
                 payroll=[{"id": "PL-1020-1", "batch": "PB-2026-08", "type": "commission", "amount": "5000.00", "posted": "2026-08-31"}],
                 narrative="I think a $200 bonus is missing on Tidal Water."))
    S.append(std("CASE-1021", "Refund before cutoff", "E-2021", "Isla Murray", "30000.00",
                 account="Umbra Studios", claim="500.00", tags=["refund", "overpayment"],
                 refunds=[{"id": "RF-1021", "inv": "INV-1021", "amount": "10000.00", "value": "2026-06-01"}],
                 payroll=[{"id": "PL-1021-1", "batch": "PB-2026-05", "type": "commission", "amount": "3000.00", "posted": "2026-05-31"}],
                 narrative="Umbra commission seems $500 light."))
    S.append(std("CASE-1022", "Duplicate commission line", "E-2022", "Omar Haddad", "30000.00",
                 account="Vertex Cloud", claim="300.00", tags=["duplicate_payout", "overpayment"],
                 payroll=[{"id": "PL-1022-1", "batch": "PB-2026-05", "type": "commission", "amount": "3000.00", "posted": "2026-05-31"},
                          {"id": "PL-1022-2", "batch": "PB-2026-06", "type": "commission", "amount": "3000.00", "posted": "2026-06-30"}],
                 narrative="I'm missing $300 of SPIFF on Vertex."))
    S.append(std("CASE-1023", "Opportunity not closed-won", "E-2023", "Nora Svensson", "40000.00",
                 account="Willow Schools", claim="4000.00", tags=["ineligible"],
                 opp={"stage": "negotiation"}, contract=None, invoices=[], payments=[],
                 narrative="Willow is basically done; please pay my $4,000."))
    S.append(std("CASE-1024", "Late payment after cutoff", "E-2024", "Diego Santos", "40000.00",
                 account="Xenon Labs", claim="1000.00", tags=["late_arriving", "partial_payment"],
                 payments=[{"id": "PAY-1024-1", "inv": "INV-1024", "amount": "30000.00", "value": "2026-06-15"},
                           {"id": "PAY-1024-2", "inv": "INV-1024", "amount": "10000.00", "value": "2026-07-05"}],
                 payroll=[{"id": "PL-1024-1", "batch": "PB-2026-06", "type": "commission", "amount": "3000.00", "posted": "2026-06-30"}],
                 narrative="Xenon paid in full; I'm owed $1,000 more."))
    S.append(std("CASE-1025", "Large adjustment above approver limit", "E-2025", "Amara Eze", "120000.00",
                 account="Yellowstone Rail", claim="6000.00", tags=["underpayment", "approval_limit"],
                 payroll=[{"id": "PL-1025-1", "batch": "PB-2026-05", "type": "commission", "amount": "6000.00", "posted": "2026-05-31"}],
                 narrative="Yellowstone fully paid $120,000. I received half the commission."))
    return S


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for spec in specs():
        case = build(spec)
        (OUT / f"{case['case_id']}.json").write_text(json.dumps(case, indent=2) + "\n")
    print(f"wrote {len(specs())} cases to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
