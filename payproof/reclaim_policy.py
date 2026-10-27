"""Deterministic consumer-dispute policy engine (airline cancellation refunds, India) and
corpus-grounded citation verifier.

Every amount, deadline and status is computed here from cited source records, with rule
parameters read from data/consumer/rulebook.json (never hard-coded, never from a model).
Agent output (RECLAIM research, citations, drafts) is a claim to verify, not evidence.

    steps:  identity -> booking -> payment -> cancellation -> notice -> alternate -> refund_due
            -> extraordinary -> compensation -> received -> deadline -> due -> paid
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from .money import D, cents, fmt
from .world_model import name_similarity

ROOT = Path(__file__).resolve().parent.parent
RULEBOOK_PATH = ROOT / "data" / "consumer" / "rulebook.json"
SUPPORTED_DOMAINS = {"airlines"}
REQUIRED_SYSTEMS = ("airline_pss", "flight_ops", "payments")


@lru_cache(maxsize=4)
def _load(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_rulebook(path: Path = RULEBOOK_PATH) -> dict:
    rb = json.loads(_load(str(path)))
    rb["by_id"] = {r["rule_id"]: r for r in rb["rules"]}
    return rb


def ts(value) -> datetime | None:
    """ISO date or datetime (with offset or Z) -> aware UTC datetime."""
    if not value:
        return None
    s = str(value).replace("Z", "+00:00")
    dt = datetime.fromisoformat(s if "T" in s else s + "T00:00:00+00:00")
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def hours(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 3600, 2)


@dataclass
class CScenario:
    """A hypothetical change replayed through the same engine. Empty == the actual evidence."""
    id: str = "actual"
    patch: dict = field(default_factory=dict)      # record_id -> {field: value}
    drop: tuple = ()                               # record ids treated as absent
    add: tuple = ()                                # (system, record) hypothetical records
    choose: dict = field(default_factory=dict)     # conflict key -> option (materiality tests)
    stale: tuple = ()                              # systems whose feed is treated as stale


class CView:
    def __init__(self, index, scenario: CScenario):
        self.index, self.s = index, scenario
        self._added = {r["id"]: r for _, r in scenario.add}

    def records(self):
        out = [r for rid, r in self.index.records.items() if rid not in self.s.drop] + list(self._added.values())
        return [{**r, **self.s.patch.get(r["id"], {})} for r in out]

    def of_type(self, rtype):
        return sorted((r for r in self.records() if r.get("type") == rtype), key=lambda r: r["id"])

    def get(self, rid):
        r = self._added.get(rid) or (None if rid in self.s.drop else self.index.records.get(rid))
        return {**r, **self.s.patch.get(rid, {})} if r else None


# --------------------------------------------------------------------------- compute

def compute(index, rulebook: dict, scenario: CScenario | None = None) -> dict:
    s = scenario or CScenario()
    v = CView(index, s)
    rules = rulebook["by_id"]
    steps, blockers, conflicts = [], [], []
    case = index.case
    claim = case["dispute"]
    as_of = ts(case["as_of"])

    def step(key, label, rule, value, cites, formula="", excluded=None, **extra):
        steps.append({"key": key, "label": label, "rule": rule, "value": value, "cites": sorted(set(cites)),
                      "formula": formula, "excluded": excluded or [], **extra})

    def block(code, detail, cites=()):
        blockers.append({"code": code, "detail": detail, "cites": sorted(set(cites))})

    def result(**extra):
        due = paid = delta = None
        st = {x["key"]: x for x in steps}
        if not blockers and "due" in st and "paid" in st:
            due, paid = st["due"]["value"], st["paid"]["value"]
            delta = fmt(D(due) - D(paid))
        return {"scenario": s.id, "steps": steps, "blockers": blockers, "conflicts": conflicts, "due": due,
                "paid": paid, "delta": delta, "rulebook_version": rulebook["rulebook_version"], **extra}

    # 0. domain + feed health: abstain rather than decide on the wrong rules or unavailable data
    if case.get("domain") not in SUPPORTED_DOMAINS:
        block("DOMAIN_UNSUPPORTED", f"no deterministic rules encoded for domain {case.get('domain')!r}; human review required",
              [claim["id"]])
        return result()
    for system in REQUIRED_SYSTEMS:
        feed = case.get("feeds", {}).get(system, {})
        if feed.get("status") == "unavailable":
            block("SOURCE_UNAVAILABLE", f"{system} could not be queried ({feed.get('reason', 'unavailable')})")
        elif system in s.stale or index.is_stale(system):
            block("STALE_SOURCE", f"{system} snapshot as of {feed.get('as_of')} exceeds the "
                                  f"{rulebook['freshness_max_age_hours'].get(system)}h freshness limit; refresh required")
    if any(b["code"] == "SOURCE_UNAVAILABLE" for b in blockers):
        return result()

    # 1. booking + identity
    bookings = [b for b in v.of_type("booking") if b.get("booking_ref") == claim.get("booking_ref")]
    if not bookings:
        block("BOOKING_NOT_FOUND", f"no booking record for {claim.get('booking_ref')} in airline_pss", [claim["id"]])
        return result()
    if len(bookings) > 1:
        conflicts.append({"code": "DUPLICATE_BOOKING", "key": "booking", "detail": f"{len(bookings)} booking records share "
                          f"{claim.get('booking_ref')}", "cites": [b["id"] for b in bookings], "options": [b["id"] for b in bookings]})
    bk = next((b for b in bookings if b["id"] == s.choose.get("booking")), bookings[0])
    sim = name_similarity(claim.get("claimant_name", ""), bk.get("passenger_name", ""))
    ident = "RESOLVED" if sim >= 0.85 else "AMBIGUOUS" if sim >= 0.6 else "MISMATCH"
    step("identity", "Claimant is the booked passenger", "IDENTITY", ident, [claim["id"], bk["id"]],
         f"name similarity {sim:.2f} (auto-link >= 0.85)", similarity=round(sim, 3))
    if ident != "RESOLVED":
        block("IDENTITY_" + ident, f"claimant '{claim.get('claimant_name')}' vs booked passenger "
                                    f"'{bk.get('passenger_name')}' (similarity {sim:.2f}); not linked", [claim["id"], bk["id"]])
    step("booking", "Booked fare (airline record)", "BOOKING", fmt(D(bk["total_paid"])), [bk["id"]],
         f"base {bk['base_fare']} + fuel {bk['fuel_charge']} + taxes {bk['taxes']}")
    if cents(D(bk["base_fare"]) + D(bk["fuel_charge"]) + D(bk["taxes"])) != cents(D(bk["total_paid"])):
        conflicts.append({"code": "FARE_COMPONENTS_MISMATCH", "key": "fare", "detail": f"{bk['id']} components do not sum to "
                          f"total_paid {bk['total_paid']}", "cites": [bk["id"]], "options": ["components", "total"]})

    # 2. payment actually captured (card network)
    pays = [p for p in v.of_type("card_payment") if p.get("booking_id") == bk["id"]]
    if not pays:
        block("PAYMENT_NOT_FOUND", f"no card-network capture for {bk['id']}", [bk["id"]])
        return result()
    pay = pays[0]
    paid_amount = D(pay["amount"])
    if paid_amount != D(bk["total_paid"]):
        conflicts.append({"code": "PAYMENT_AMOUNT_MISMATCH", "key": "payment",
                          "detail": f"card capture {pay['amount']} ({pay['id']}) != airline total {bk['total_paid']} ({bk['id']})",
                          "cites": [pay["id"], bk["id"]], "options": ["card", "airline"]})
        if s.choose.get("payment") == "airline":
            paid_amount = D(bk["total_paid"])
    step("payment", "Amount captured from the claimant", "PAYMENT", fmt(paid_amount), [pay["id"]],
         f"card network capture {str(pay.get('captured_at'))[:10]}")

    # 3. cancellation event
    events = [e for e in v.of_type("flight_event") if e.get("booking_id") == bk["id"]]
    cancelled = [e for e in events if e.get("event") == "CANCELLED"]
    if not cancelled:
        block("CANCELLATION_NOT_FOUND", f"flight_ops has no cancellation event for {bk['flight_no']}", [bk["id"]])
        return result()
    if any(e.get("event") == "OPERATED" for e in events):
        conflicts.append({"code": "FLIGHT_STATUS_CONFLICT", "key": "flight_status", "detail": "flight_ops reports the flight "
                          "both CANCELLED and OPERATED", "cites": [e["id"] for e in events], "options": ["CANCELLED", "OPERATED"]})
        if s.choose.get("flight_status") == "OPERATED":
            block("NOT_CANCELLED", "under this option the flight operated", [e["id"] for e in events])
            return result()
    ev = cancelled[0]
    if not ev.get("notified_at"):
        block("NOTICE_TIME_MISSING", f"{ev['id']} does not record when passengers were notified", [ev["id"]])
        return result()
    dep = ts(bk["scheduled_departure"])
    notified = ts(ev["notified_at"])
    notice_h = hours(notified, dep)
    step("cancellation", "Flight cancelled by the carrier", "IN-AIR-CANCEL-REFUND", "CANCELLED", [ev["id"]],
         f"cause {ev.get('cause_code')}")
    p_notice = rules["IN-AIR-CANCEL-NOTICE"]["parameters"]
    doc_notice = index.doc_fact("notified_at")
    if doc_notice:  # the claimant's own document vs the carrier's ops log
        doc_h = hours(ts(doc_notice["value"]), dep)
        band = lambda h: 0 if h < p_notice["min_notice_hours"] else 1 if h < p_notice["full_notice_hours"] else 2
        if band(doc_h) != band(notice_h):
            conflicts.append({"code": "NOTICE_TIME_CONFLICT", "key": "notice",
                              "detail": f"carrier log {ev['id']} says notified {notice_h:.1f}h before departure; claimant "
                                        f"document {doc_notice['doc_id']} says {doc_h:.1f}h",
                              "cites": [ev["id"], doc_notice["doc_id"]], "options": ["carrier", "document"]})
            if s.choose.get("notice") == "document":
                notice_h = doc_h
    step("notice", "Notice given before departure (hours)", "IN-AIR-CANCEL-NOTICE", f"{notice_h:.2f}", [ev["id"]],
         f"departure {bk['scheduled_departure']} - notified {ev['notified_at']}")

    # 4. alternate flight
    alts = [a for a in v.of_type("alternate_offer") if a.get("booking_id") == bk["id"]]
    in_window = [a for a in alts if a.get("offered_departure")
                 and abs(hours(dep, ts(a["offered_departure"]))) * 60 <= p_notice["alternate_window_minutes"]]
    accepted = [a for a in alts if a.get("accepted") is True]
    step("alternate", "Alternate flight offered within two hours / accepted", "IN-AIR-CANCEL-NOTICE",
         "ACCEPTED" if accepted else "OFFERED_IN_WINDOW" if in_window else "NONE_IN_WINDOW", [a["id"] for a in alts] or [ev["id"]])

    # 5. refund entitlement
    refund_due = D(0) if accepted else paid_amount
    step("refund_due", "Refund entitlement", "IN-AIR-CANCEL-REFUND", fmt(refund_due), [pay["id"], ev["id"]] + [a["id"] for a in accepted],
         "0 (alternate accepted)" if accepted else "amount captured")

    # 6. extraordinary circumstances: the carrier's assertion must be corroborated
    p_ext = rules["IN-AIR-EXTRAORDINARY"]["parameters"]
    asserted = ev.get("cause_code") in p_ext["categories"]
    win = timedelta(hours=p_ext["corroboration_window_hours"])
    corroborating = [n for n in v.of_type("ops_notice") if n.get("airport") in (bk.get("origin"), bk.get("destination"))
                     and n.get("category") in p_ext["categories"] and ts(n["valid_from"]) <= dep + win and ts(n["valid_to"]) >= dep - win]
    exempt_ext = asserted and bool(corroborating)
    if asserted and not corroborating:
        conflicts.append({"code": "EXTRAORDINARY_UNCORROBORATED", "key": "extraordinary",
                          "detail": f"carrier cause {ev.get('cause_code')} ({ev['id']}) has no matching airport_ops notice",
                          "cites": [ev["id"]], "options": ["exempt", "not_exempt"]})
        exempt_ext = s.choose.get("extraordinary") == "exempt"
    step("extraordinary", "Extraordinary circumstances (compensation exemption)", "IN-AIR-EXTRAORDINARY",
         "EXEMPT" if exempt_ext else "NOT_EXEMPT", [ev["id"]] + [n["id"] for n in corroborating],
         ("corroborated by " + ", ".join(n["id"] for n in corroborating)) if corroborating else
         ("carrier asserts, uncorroborated" if asserted else "operational cause"))

    # 7. compensation
    exempt_notice = notice_h >= p_notice["full_notice_hours"] or (notice_h >= p_notice["min_notice_hours"] and bool(in_window))
    slab = next(x for x in rules["IN-AIR-CANCEL-COMP"]["parameters"]["slabs"]
                if x["max_block_minutes"] is None or int(bk["block_minutes"]) <= x["max_block_minutes"])
    fare_cap = D(bk["base_fare"]) + D(bk["fuel_charge"])
    comp_due = D(0) if (exempt_notice or exempt_ext) else min(D(slab["cap"]), fare_cap)
    step("compensation", "Compensation entitlement", "IN-AIR-CANCEL-COMP", fmt(comp_due), [bk["id"], ev["id"]],
         "0 (notice/alternative adequate)" if exempt_notice else "0 (extraordinary circumstances)" if exempt_ext else
         f"min(block-time cap {slab['cap']} for {bk['block_minutes']} min, basic fare + fuel {fmt(fare_cap)})")

    # 8. money actually received (the card network is authoritative for receipt)
    credits = [c for c in v.of_type("card_credit") if c.get("payment_id") == pay["id"] and ts(c["posted_at"]) <= as_of]
    refund_rcvd = sum((D(c["amount"]) for c in credits if c.get("kind", "refund") == "refund"), D(0))
    comp_rcvd = sum((D(c["amount"]) for c in credits if c.get("kind") == "compensation"), D(0))
    consent = [c for c in v.of_type("passenger_consent") if c.get("booking_id") == bk["id"] and c.get("consent") == "credit_shell"]
    excluded = []
    for r in v.of_type("airline_refund"):
        if r.get("booking_id") != bk["id"]:
            continue
        if r.get("mode") == "credit_shell":
            if consent:
                refund_rcvd += D(r["amount"])
            else:
                excluded.append({"id": r["id"], "reason": "credit shell without passenger consent is not a refund (IN-AIR-CREDIT-SHELL)"})
        elif r.get("status") == "PROCESSED" and not any(D(c["amount"]) == D(r["amount"]) for c in credits):
            age = (as_of - ts(r["processed_at"])).days
            if age <= rulebook["settlement_window_days"]:
                block("REFUND_IN_TRANSIT", f"carrier reports {r['id']} processed {age} day(s) ago; card settlement window "
                                           f"{rulebook['settlement_window_days']} days not yet elapsed", [r["id"], pay["id"]])
            else:
                conflicts.append({"code": "AIRLINE_REFUND_UNCONFIRMED", "key": "airline_refund",
                                  "detail": f"carrier reports {r['id']} ({r['amount']}) processed {age} days ago; no matching "
                                            f"credit on the claimant's card ({pay['id']})",
                                  "cites": [r["id"], pay["id"]], "options": ["card_ledger", "carrier_claim"], "amount": r["amount"]})
                if s.choose.get("airline_refund") == "carrier_claim":
                    refund_rcvd += D(r["amount"])
    step("received", "Refund and compensation received", "IN-AIR-REFUND-TAT", fmt(refund_rcvd + comp_rcvd),
         [c["id"] for c in credits] + [c["id"] for c in consent] or [pay["id"]],
         f"refund {fmt(refund_rcvd)} + compensation {fmt(comp_rcvd)} posted by {case['as_of'][:10]}", excluded=excluded,
         refund=fmt(refund_rcvd), compensation=fmt(comp_rcvd))

    # 9. refund deadline (reported; it never changes an amount)
    tat = rules["IN-AIR-REFUND-TAT"]["parameters"]["tat_days"].get(bk.get("channel"))
    due_by = (notified + timedelta(days=tat)).date().isoformat() if tat is not None else None
    overdue = bool(due_by) and as_of.date().isoformat() > due_by and refund_rcvd < refund_due
    step("deadline", "Refund deadline", "IN-AIR-REFUND-TAT", due_by or "UNKNOWN_CHANNEL", [bk["id"], ev["id"]],
         f"{bk.get('channel')}: {tat} day(s) from notification" if tat is not None else "payment channel not covered by the rulebook",
         overdue=overdue)

    due = refund_due + comp_due
    step("due", "Total due to the claimant", "IN-AIR-CANCEL-REFUND", fmt(due), [pay["id"], ev["id"]],
         f"refund {fmt(refund_due)} + compensation {fmt(comp_due)}", refund=fmt(refund_due), compensation=fmt(comp_due))
    step("paid", "Total already received", "IN-AIR-REFUND-TAT", fmt(refund_rcvd + comp_rcvd), [c["id"] for c in credits] or [pay["id"]])
    return result(notice_hours=notice_h, refund_due=fmt(refund_due), compensation_due=fmt(comp_due),
                  refund_received=fmt(refund_rcvd), compensation_received=fmt(comp_rcvd), deadline=due_by, overdue=overdue,
                  booking_id=bk["id"], payment_id=pay["id"], event_id=ev["id"])


def step_of(calc, key):
    return next((x for x in calc["steps"] if x["key"] == key), None)


def verdict_for(status: str, calc: dict, claimed) -> str:
    if status != "VERIFIED" or calc["delta"] is None:
        return "UNDETERMINED"
    delta = D(calc["delta"])
    if delta <= 0:
        return "REJECTED"
    return "SUPPORTED" if delta >= D(claimed) else "PARTIALLY_SUPPORTED"


# --------------------------------------------------------------------------- citations

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "fourteen": 14, "fifteen": 15, "thirty": 30}
_QTY = re.compile(r"(?:(?:\b(?:inr|rs\.?)|₹)\s*([\d,]+(?:\.\d+)?))|(?:\b(\d[\d,]*|" + "|".join(_WORDS)
                  + r")\s*(day|hour|minute|week)s?\b)", re.I)
_NORM = re.compile(r"[^a-z0-9]+")


def _norm(text: str) -> str:
    return " " + _NORM.sub(" ", (text or "").lower()).strip() + " "


def quantities(text: str) -> set[tuple[str, int]]:
    """(unit, value) pairs: INR amounts in whole rupees, durations normalised to days/hours/minutes."""
    out = set()
    for m in _QTY.finditer(text or ""):
        if m.group(1):
            out.add(("inr", int(D(m.group(1).replace(",", "")))))
            continue
        raw, unit = m.group(2).lower(), m.group(3).lower()
        n = _WORDS.get(raw) or int(raw.replace(",", ""))
        if unit == "week":
            out |= {("day", n * 7), ("hour", n * 168)}
        elif unit == "day":
            out |= {("day", n), ("hour", n * 24)}
        else:
            out.add((unit, n))
    return out


def _rule_quantities(rule: dict) -> set[tuple[str, int]]:
    q = quantities(rule["text"])
    p = rule["parameters"]
    q |= {("day", n) for n in (p.get("tat_days") or {}).values()}
    if "reversal_days" in p:
        q.add(("day", p["reversal_days"]))
    for key, unit in (("full_notice_hours", "hour"), ("min_notice_hours", "hour"), ("alternate_window_minutes", "minute"),
                      ("corroboration_window_hours", "hour")):
        if key in p:
            q.add((unit, int(p[key])))
            if unit == "hour" and p[key] % 24 == 0:
                q.add(("day", int(p[key]) // 24))
    for slab in p.get("slabs", []):
        q.add(("inr", int(D(slab["cap"]))))
        if slab["max_block_minutes"]:
            q |= {("minute", slab["max_block_minutes"]), ("hour", slab["max_block_minutes"] // 60)}
    if "compensation_per_day" in p:
        q.add(("inr", int(D(p["compensation_per_day"]))))
    return q


def citation_text(citation) -> str:
    if isinstance(citation, str):
        return citation
    if isinstance(citation, dict):
        return " ".join(str(citation.get(k) or "") for k in ("citation", "title", "authority", "source", "instrument", "section",
                                                              "provision", "text", "quote", "retrieved_chunk"))
    return str(citation or "")


def verify_citation(citation, rulebook: dict, domain: str | None = None) -> dict:
    """Resolve a citation to a rulebook clause, then check every quantity it quotes.

    VERIFIED     instrument + provision resolve; every quoted quantity matches the rule
    MISQUOTED    resolves, but quotes a number the rule does not contain (e.g. "refund within 3 days")
    PARTIAL      the instrument exists but no provision could be resolved (not usable for a material claim)
    WRONG_DOMAIN resolves to a rule for a different dispute domain
    UNVERIFIED   nothing in the corpus matches; never used in an explanation"""
    text = citation_text(citation).strip()
    base = {"citation": text[:400], "verified": False, "rule_id": None, "instrument": None, "provision": None,
            "rulebook_version": rulebook["rulebook_version"], "method": "rulebook-resolution+quantity-check/v1"}
    if len(text) < 4:
        return {**base, "status": "UNVERIFIED", "reason": "empty citation"}
    nt = _norm(text)
    by_instrument = [r for r in rulebook["rules"]
                     if any(_norm(a) in nt for a in [r["instrument"]] + r["instrument_aliases"])]
    if not by_instrument:
        return {**base, "status": "UNVERIFIED", "reason": "no instrument in the rulebook matches this citation"}
    scored = sorted(((sum(_norm(k) in nt for k in r["keywords"]), r["rule_id"], r) for r in by_instrument),
                    key=lambda x: (-x[0], x[1]))
    hits, _, rule = scored[0]
    if hits == 0:
        return {**base, "status": "PARTIAL", "instrument": rule["instrument"],
                "reason": "instrument recognised but no provision could be resolved from the citation text"}
    out = {**base, "rule_id": rule["rule_id"], "instrument": rule["instrument"], "provision": rule["provision"],
           "rule_text": rule["text"], "text_kind": rule["text_kind"]}
    if domain and rule["domain"] != domain:
        return {**out, "status": "WRONG_DOMAIN", "reason": f"rule applies to {rule['domain']}, case is {domain}"}
    # Quantities are grounded against the whole cited instrument: a citation of one clause may restate a
    # condition from a sibling clause (e.g. the 24-hour notice band), but never a number the instrument lacks.
    quoted = quantities(text)
    allowed = set().union(*(_rule_quantities(r) for r in by_instrument if r["instrument"] == rule["instrument"]))
    bad = sorted(q for q in quoted if q not in allowed)
    out["quantities_checked"] = sorted(f"{val} {unit}" for unit, val in quoted)
    if bad:
        return {**out, "status": "MISQUOTED", "reason": "quotes " + ", ".join(f"{val} {unit}" for unit, val in bad)
                + f", which {rule['instrument']} does not contain", "misquoted": [f"{val} {unit}" for unit, val in bad]}
    return {**out, "status": "VERIFIED", "verified": True, "reason": f"resolves to {rule['rule_id']}"
            + (f"; {len(quoted)} quoted quantit{'y' if len(quoted) == 1 else 'ies'} match" if quoted else "")}
