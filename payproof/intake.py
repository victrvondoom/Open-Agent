"""Runtime dispute intake: turn a validated form into a full six-system case snapshot.

Every value is validated (exact decimals, ISO dates, bounded lists and strings) before it
is turned into source records by the same builder the benchmark fixtures use, so a
user-filed dispute goes through the identical investigation, proof and approval pipeline.
Cases are written to var/cases/ (git-ignored) and survive restarts.
"""

import json
import re
import threading
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .casebuilder import build

ROOT = Path(__file__).resolve().parent.parent
USER_CASES = ROOT / "var" / "cases"
FIRST_USER_CASE = 2001
MAX_MONEY = Decimal("10000000")
MAX_ITEMS = 20
_LOCK = threading.Lock()

PERIODS = {f"2026-Q{q}": f"2026-{m}" for q, m in ((1, "03-31"), (2, "06-30"), (3, "09-30"), (4, "12-31"))}
STAGES = ("closed_won", "closed_lost", "negotiation", "proposal")
EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,24}", re.I)
TEXT_RE = re.compile(r"[^<>\x00-\x1f\x7f]*")  # any printable text except markup brackets and control characters


class IntakeError(ValueError):
    def __init__(self, field, message):
        super().__init__(f"{field}: {message}")
        self.field, self.message = field, message


def _text(form, key, max_len, required=True, default=None):
    v = form.get(key, default)
    if v in (None, ""):
        if required:
            raise IntakeError(key, "is required")
        return default
    if isinstance(v, str):
        v = re.sub(r"[\r\n\t]+", " ", v)  # textarea newlines are formatting, not data
    if not isinstance(v, str) or len(v) > max_len or not TEXT_RE.fullmatch(v):
        raise IntakeError(key, f"must be plain text up to {max_len} characters (no < > or control characters)")
    return v.strip()


def _money(value, key, allow_zero=True):
    if isinstance(value, bool) or isinstance(value, float):
        raise IntakeError(key, "send amounts as strings like \"1234.50\" (no floats)")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise IntakeError(key, "is not a number")
    if not d.is_finite() or d.as_tuple().exponent < -2:
        raise IntakeError(key, "must have at most 2 decimal places")
    if d < 0 or d > MAX_MONEY or (d == 0 and not allow_zero):
        raise IntakeError(key, f"must be between {'0' if allow_zero else '0.01'} and {MAX_MONEY}")
    return f"{d:.2f}"


def _date(value, key):
    try:
        d = date.fromisoformat(str(value))
    except ValueError:
        raise IntakeError(key, "must be an ISO date (YYYY-MM-DD)")
    if not date(2025, 1, 1) <= d <= date(2027, 12, 31):
        raise IntakeError(key, "must be between 2025-01-01 and 2027-12-31")
    return d.isoformat()


def _email(form, key, default=None):
    v = form.get(key) or default
    if not v or not isinstance(v, str) or not EMAIL_RE.fullmatch(v):
        raise IntakeError(key, "must be an email address")
    return v.lower()


def _items(form, key, fields):
    rows = form.get(key) or []
    if not isinstance(rows, list) or len(rows) > MAX_ITEMS:
        raise IntakeError(key, f"must be a list of at most {MAX_ITEMS} items")
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise IntakeError(f"{key}[{i}]", "must be an object")
        item = {}
        for f, kind, required in fields:
            v = row.get(f)
            if v in (None, ""):
                if required:
                    raise IntakeError(f"{key}[{i}].{f}", "is required")
                continue
            item[f] = _money(v, f"{key}[{i}].{f}", allow_zero=False) if kind == "money" else _date(v, f"{key}[{i}].{f}")
        out.append(item)
    return out


def next_case_id(existing: set[str]) -> str:
    n = FIRST_USER_CASE
    while f"CASE-{n}" in existing:
        n += 1
    if n > 9999:
        raise IntakeError("case", "no case ids left")
    return f"CASE-{n}"


def spec_from_form(form: dict, case_id: str) -> dict:
    if not isinstance(form, dict):
        raise IntakeError("body", "must be a JSON object")
    n = case_id[5:]
    rep_name = _text(form, "rep_name", 60)
    rep_email = _email(form, "rep_email")
    crm_name = _text(form, "crm_name", 60, required=False, default=rep_name)
    crm_email = _email(form, "crm_email", default=rep_email)
    period = form.get("period", "2026-Q2")
    if period not in PERIODS:
        raise IntakeError("period", f"must be one of {', '.join(PERIODS)}")
    stage = form.get("stage", "closed_won")
    if stage not in STAGES:
        raise IntakeError("stage", f"must be one of {', '.join(STAGES)}")
    close = _date(form.get("close_date"), "close_date")
    crm_amount = _money(form.get("crm_amount"), "crm_amount", allow_zero=False)
    split = _money(form.get("split_pct", "100"), "split_pct", allow_zero=False)
    if Decimal(split) > 100:
        raise IntakeError("split_pct", "must be at most 100")

    user, co = f"U-9{n}", f"U-8{n}"
    crm_users = [{"id": user, "name": crm_name, "email": crm_email}]
    splits = [(user, split.rstrip("0").rstrip(".") if "." in split else split)]
    if Decimal(split) < 100:
        co_name = _text(form, "co_seller_name", 60, required=False, default="Co-seller")
        crm_users.append({"id": co, "name": co_name, "email": f"co-seller-{n}@peoplepay.example"})
        rest = Decimal(100) - Decimal(split)
        splits.append((co, f"{rest.normalize():f}"))

    contract = None
    if form.get("contract_tcv") not in (None, ""):
        contract = {"id": f"CTR-{n}", "tcv": _money(form["contract_tcv"], "contract_tcv", allow_zero=False),
                    "signed": _date(form.get("contract_signed") or close, "contract_signed")}
    amendments = []
    am = form.get("amendment")
    if am:
        if not contract:
            raise IntakeError("amendment", "requires a contract")
        if not isinstance(am, dict):
            raise IntakeError("amendment", "must be an object")
        amendments.append({"id": f"AMD-{n}-1", "new_tcv": _money(am.get("new_tcv"), "amendment.new_tcv", allow_zero=False),
                           "effective": _date(am.get("effective"), "amendment.effective"),
                           "signed": _date(am.get("signed"), "amendment.signed")})

    inv_id = f"INV-{n}"
    invoices = []
    inv_amount = form.get("invoice_amount") or (contract or {}).get("tcv")
    if inv_amount:
        invoices.append({"id": inv_id, "amount": _money(inv_amount, "invoice_amount", allow_zero=False),
                         "issued": _date(form.get("invoice_date") or close, "invoice_date")})
    pays = _items(form, "payments", [("amount", "money", True), ("value_date", "date", True), ("recorded_date", "date", False)])
    cns = _items(form, "credit_notes", [("amount", "money", True), ("issued_date", "date", True)])
    refs = _items(form, "refunds", [("amount", "money", True), ("value_date", "date", True)])
    if (pays or cns or refs) and not invoices:
        raise IntakeError("invoice_amount", "payments, credit notes and refunds need an invoice")
    lines = _items(form, "payroll", [("amount", "money", True), ("posted_date", "date", True)])
    for i, row in enumerate(form.get("payroll") or []):
        lt = row.get("type", "commission")
        if lt not in ("commission", "clawback", "adjustment"):
            raise IntakeError(f"payroll[{i}].type", "must be commission, clawback or adjustment")
        lines[i]["type"] = lt
    exceptions = []
    ex = form.get("exception")
    if ex:
        if not isinstance(ex, dict):
            raise IntakeError("exception", "must be an object")
        rate = _money(ex.get("rate"), "exception.rate", allow_zero=False)
        if Decimal(rate) >= 1:
            raise IntakeError("exception.rate", "is a fraction, e.g. 0.12")
        approved = ex.get("approved") is True
        exceptions.append({"id": f"EXC-{n}", "rate": rate, "status": "APPROVED" if approved else "PENDING",
                           **({"approval_ref": f"APR-{n}", "approved_by": "VP-SALES-1"} if approved else {})})

    return {
        "case_id": case_id,
        "title": _text(form, "title", 80, required=False, default=f"{_text(form, 'account', 60)} — user-filed dispute"),
        "tags": ["user-filed"],
        "claimant": {"id": f"E-9{n}", "name": rep_name, "email": rep_email},
        "crm_users": crm_users,
        "opp": {"id": f"OPP-{n}", "account": _text(form, "account", 60), "amount": crm_amount, "stage": stage,
                "close_date": close, "owner": user, "splits": splits},
        "contract": contract, "amendments": amendments, "invoices": invoices,
        "payments": [{"id": f"PAY-{n}-{i + 1}", "inv": inv_id, "amount": p["amount"], "value": p["value_date"],
                      "recorded": p.get("recorded_date", p["value_date"])} for i, p in enumerate(pays)],
        "credit_notes": [{"id": f"CN-{n}-{i + 1}", "inv": inv_id, "amount": c["amount"], "issued": c["issued_date"]} for i, c in enumerate(cns)],
        "refunds": [{"id": f"RF-{n}-{i + 1}", "inv": inv_id, "amount": r["amount"], "value": r["value_date"]} for i, r in enumerate(refs)],
        "payments_feed": "ok" if form.get("payments_feed_available", True) is not False else "unavailable",
        "exceptions": exceptions,
        "payroll": [{"id": f"PL-{n}-{i + 1}", "batch": f"PB-{l['posted_date'][:7]}", "type": l["type"], "amount":
                     (f"-{l['amount']}" if l["type"] == "clawback" else l["amount"]), "posted": l["posted_date"]}
                    for i, l in enumerate(lines)],
        "claim": _money(form.get("claimed_shortfall"), "claimed_shortfall", allow_zero=False),
        "narrative": _text(form, "narrative", 400, required=False, default="Filed through PayProof dispute intake."),
        "cutoff": PERIODS[period], "period": period,
        "filed": _date(form.get("filed_date") or date.today().isoformat(), "filed_date"),
    }


def create_case(form: dict, existing_ids: set[str], directory: Path = USER_CASES) -> dict:
    with _LOCK:
        case_id = next_case_id(existing_ids | {p.stem for p in directory.glob("CASE-*.json")} if directory.exists() else existing_ids)
        case = build(spec_from_form(form, case_id))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{case_id}.json").write_text(json.dumps(case, indent=2) + "\n")
        return case


def template_from_case(case: dict) -> dict:
    """Prefill the intake form from an existing case's actual source records."""
    src = {k: v["records"] for k, v in case["sources"].items()}
    first = lambda sys, t: next((r for r in src[sys] if r["type"] == t), None)  # noqa: E731
    emp, opp, ctr, inv = first("hris", "employee"), first("crm", "opportunity"), first("clm", "contract"), first("billing", "invoice")
    crm_user = next((r for r in src["crm"] if r["type"] == "crm_user" and r["id"] == opp["owner"]), None)
    amd = first("clm", "amendment")
    cal = first("payroll", "pay_calendar")
    return {
        "title": "", "account": opp["account"], "rep_name": emp["name"], "rep_email": emp["email"],
        "crm_name": crm_user["name"] if crm_user else emp["name"], "crm_email": crm_user["email"] if crm_user else emp["email"],
        "crm_amount": opp["amount"], "stage": opp["stage"], "close_date": opp["close_date"], "split_pct": "100",
        "period": cal["period"] if cal else "2026-Q2",
        "contract_tcv": ctr["tcv"] if ctr else "", "contract_signed": ctr["signed_date"] if ctr else "",
        "amendment": {"new_tcv": amd["new_tcv"], "effective": amd["effective_date"], "signed": amd["signed_date"]} if amd else None,
        "invoice_amount": inv["amount"] if inv else "", "invoice_date": inv["issued_date"] if inv else "",
        "payments": [{"amount": r["amount"], "value_date": r["value_date"], "recorded_date": r["recorded_at"][:10]}
                     for r in src["billing"] if r["type"] == "payment"],
        "credit_notes": [{"amount": r["amount"], "issued_date": r["issued_date"]} for r in src["billing"] if r["type"] == "credit_note"],
        "refunds": [{"amount": r["amount"], "value_date": r["value_date"]} for r in src["billing"] if r["type"] == "refund"],
        "payroll": [{"amount": r["amount"].lstrip("-"), "posted_date": r["effective_at"], "type": r["line_type"]}
                    for r in src["payroll"] if r["type"] == "payroll_line"],
        "claimed_shortfall": case["dispute"]["claimed_shortfall"], "narrative": case["dispute"]["narrative"],
        "payments_feed_available": case["feeds"].get("billing.payments") == "ok",
    }
