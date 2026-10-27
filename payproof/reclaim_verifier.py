"""Bounded, auditable consumer-dispute investigation (RECLAIM x PayProof).

    RECLAIM intake + agents -> evidence bridge (lineage, data quality) -> Zetaris federation
    -> Meterless World Model -> deterministic policy engine -> counterfactual replay
    -> investigator (falsifiable hypotheses) -> Meterless Scout guard -> independent skeptic
    -> invariant verifier -> resolution planner -> Nemotron narration -> final validator

Fixed order, no loops, at most llm.MAX_CALLS_PER_RUN model calls. Every amount, status and action
comes from deterministic code. RECLAIM agent output and model text are claims to verify: a
decision is never accepted because two agents agree, only because cited records support it.
"""

import re
import time
from dataclasses import replace
from datetime import timedelta

from . import ENGINE_VERSION
from . import world_model as wm
from .llm import ModelClient
from .money import D, fmt
from .reclaim_evidence import (ConsumerEvidenceIndex, compute_evidence_hash, consumer_fingerprint, contradictions, data_quality,
                               ingest_consumer_case, normalize_agent_run, without)
from .reclaim_policy import CScenario, compute, step_of, ts, verdict_for
from .scout import injection_check, scan_records
from .sources import sha

ACTION_TYPES = {"FILE_GRIEVANCE", "REQUEST_EVIDENCE", "ESCALATE_FOR_REVIEW", "CLOSE_NO_ACTION"}
HYPOTHESIS_STATUSES = ("SUPPORTED", "REFUTED", "INSUFFICIENT_EVIDENCE", "CONTRADICTORY", "NEEDS_HUMAN_REVIEW")
NARRATOR_SYSTEM = ("You are a consumer-dispute analyst. You may only restate facts given to you. "
                   "Return strict JSON: {\"claims\": [{\"text\": str, \"cites\": [record_id,...]}]}. "
                   "Every claim must cite at least one record id or rule id from the provided facts. Do not compute new "
                   "numbers; only use amounts that appear verbatim in the input. At most 4 claims, each under 45 words.")
AMOUNT_RE = re.compile(r"(?:INR|Rs\.?|₹)\s*([\d,]+\.\d{2})")


def _inr(x):
    return f"INR {D(x):,.2f}" if x is not None else "n/a"


def claimed_total(case) -> str:
    d = case["dispute"]
    return fmt(D(d.get("claimed_refund") or 0) + D(d.get("claimed_compensation") or 0))


# --------------------------------------------------------------------------- decision core (also used by counterfactuals)

def materiality(index, rulebook, calc, scenario: CScenario) -> dict:
    """A conflict is material when choosing another option changes what is owed (or whether it can be known)."""
    out = {}
    for c in calc["conflicts"]:
        outcomes = set()
        for o in c["options"]:
            r = compute(index, rulebook, replace(scenario, choose={**scenario.choose, c["key"]: o}))
            outcomes.add((tuple(sorted(b["code"] for b in r["blockers"])), r["delta"]))
        out[c["key"]] = len(outcomes) > 1
    return out


def plan_type(status: str, calc: dict) -> tuple[str, str | None]:
    if any(b["code"] == "DOMAIN_UNSUPPORTED" for b in calc["blockers"]):
        return "ESCALATE_FOR_REVIEW", None
    if status == "NEEDS_EVIDENCE":
        return "REQUEST_EVIDENCE", None
    if status in ("DISPUTED", "REJECTED"):
        return "ESCALATE_FOR_REVIEW", None
    if D(calc["delta"]) > 0:
        return "FILE_GRIEVANCE", calc["delta"]
    return "CLOSE_NO_ACTION", None


def decide(index, rulebook, scenario: CScenario | None = None, critic: bool = True, claimed: str | None = None) -> dict:
    s = scenario or CScenario()
    calc = compute(index, rulebook, s)
    mat = materiality(index, rulebook, calc, s) if critic else {c["key"]: False for c in calc["conflicts"]}
    status = "NEEDS_EVIDENCE" if calc["blockers"] else "DISPUTED" if any(mat.values()) else "VERIFIED"
    action, amount = plan_type(status, calc)
    return {"calc": calc, "materiality": mat, "status": status, "action": action, "amount": amount,
            "verdict": verdict_for(status, calc, claimed or claimed_total(index.case))}


def _label(dec) -> str:
    return f"{dec['action']}" + (f" {_inr(dec['amount'])}" if dec["amount"] else "") + f" ({dec['status']})"


# --------------------------------------------------------------------------- counterfactuals

def scenarios(index, calc) -> list[tuple[CScenario, dict]]:
    """Hypothetical changes derived from the facts actually present in this case."""
    case, out = index.case, []
    bk, pay, ev = (index.get(calc.get(k)) for k in ("booking_id", "payment_id", "event_id"))
    as_of = case["as_of"]

    def add(sid, title, question, changed, **kw):
        out.append((CScenario(id=sid, **kw), {"id": sid, "title": title, "question": question, "changed_facts": changed}))
    if pay and calc.get("refund_due") and D(calc["refund_due"]) > D(calc.get("refund_received") or 0):
        owed = fmt(D(calc["refund_due"]) - D(calc["refund_received"]))
        add("cf_refund_processed", "Refund actually processed", "What if the disputed refund had actually reached the claimant's card?",
            ["CRD-HYPOTHETICAL"], add=(("payments", {"id": "CRD-HYPOTHETICAL", "type": "card_credit", "payment_id": pay["id"],
                                                     "kind": "refund", "amount": owed, "posted_at": as_of}),))
    if ev and bk:
        dep = ts(bk["scheduled_departure"])
        add("cf_extraordinary", "Corroborated bad weather", "What if the cancellation was caused by weather, corroborated by an airport notice?",
            [ev["id"], "OPS-HYPOTHETICAL"], patch={ev["id"]: {"cause_code": "WEATHER"}},
            add=(("airport_ops", {"id": "OPS-HYPOTHETICAL", "type": "ops_notice", "airport": bk["origin"], "category": "WEATHER",
                                  "valid_from": dep.isoformat(), "valid_to": dep.isoformat()}),))
        add("cf_two_week_notice", "Two weeks' notice", "What if passengers had been told 15 days before departure?", [ev["id"]],
            patch={ev["id"]: {"notified_at": (dep - timedelta(days=15)).isoformat()}})
        add("cf_alternate_accepted", "Alternate flight accepted", "What if the claimant had accepted an alternate flight?",
            ["ALT-HYPOTHETICAL"], add=(("flight_ops", {"id": "ALT-HYPOTHETICAL", "type": "alternate_offer", "booking_id": bk["id"],
                                                       "offered_departure": dep.isoformat(), "accepted": True}),))
        add("cf_contradicting_refund", "Contradictory carrier refund arrives",
            "What if tomorrow the carrier reported a refund processed three weeks ago that the card ledger does not show?",
            ["ARF-HYPOTHETICAL"], add=(("airline_pss", {"id": "ARF-HYPOTHETICAL", "type": "airline_refund", "booking_id": bk["id"],
                                                        "amount": calc.get("refund_due") or bk["total_paid"], "mode": "original_instrument",
                                                        "status": "PROCESSED", "processed_at": (ts(as_of) - timedelta(days=21)).isoformat()}),))
    if bk:
        add("cf_missing_booking", "Booking record missing", "What if the carrier's booking record were missing?", [bk["id"]], drop=(bk["id"],))
    add("cf_stale_payments", "Stale payments snapshot", "What if the card-network snapshot were older than its freshness limit?",
        ["feed:payments"], stale=("payments",))
    return out


def replay(index, rulebook, actual: dict, critic: bool = True) -> list[dict]:
    claimed = claimed_total(index.case)
    out = []
    for scen, meta in scenarios(index, actual["calc"]):
        dec = decide(index, rulebook, scen, critic, claimed)
        changed = (dec["action"], dec["amount"]) != (actual["action"], actual["amount"])
        out.append({**meta, "hypothetical": True, "status": dec["status"], "verdict": dec["verdict"], "action": dec["action"],
                    "amount": dec["amount"], "delta": dec["calc"]["delta"], "changes_recommendation": changed,
                    "blockers": [b["code"] for b in dec["calc"]["blockers"]],
                    "summary": (f"Recommendation changes: {_label(actual)} -> {_label(dec)}" if changed
                                else f"Recommendation unchanged: {_label(dec)}")})
    return sorted(out, key=lambda x: (not x["changes_recommendation"], x["id"]))


def attribution(index, rulebook, actual: dict, critic: bool = True) -> list[dict]:
    """Leave-one-out: which cited records, if removed, would flip the recommendation."""
    claimed = claimed_total(index.case)
    cited = sorted({c for st in actual["calc"]["steps"] for c in st["cites"] if c in index.records and index.system_of.get(c) != "claim"})
    out = []
    for rid in cited:
        dec = decide(index, rulebook, CScenario(id=f"loo_{rid}", drop=(rid,)), critic, claimed)
        flips = (dec["action"], dec["amount"]) != (actual["action"], actual["amount"])
        out.append({"record_id": rid, "system": index.system_of.get(rid), "pivotal": flips, "without_it": _label(dec),
                    "explanation": (f"Removing {rid} changes the recommendation to {_label(dec)}" if flips
                                    else f"Removing {rid} leaves the recommendation unchanged")})
    return sorted(out, key=lambda x: (not x["pivotal"], x["record_id"]))


def what_if(index, rulebook, change: dict, critic: bool = True) -> dict:
    """Counterfactual laboratory: one allow-listed hypothetical change, replayed through the same engine."""
    base = decide(index, rulebook, None, critic)
    calc = base["calc"]
    bk, pay, ev = (index.get(calc.get(k)) for k in ("booking_id", "payment_id", "event_id"))
    kind, value = change.get("fact"), change.get("value")
    if kind == "notice_hours" and ev and bk:
        h = float(value)
        if not 0 <= h <= 24 * 90:
            raise ValueError("notice_hours must be between 0 and 2160")
        scen = CScenario(id="lab", patch={ev["id"]: {"notified_at": (ts(bk["scheduled_departure"]) - timedelta(hours=h)).isoformat()}})
        desc = f"notice set to {h:g} hours before departure"
    elif kind == "refund_received" and pay:
        amt = fmt(D(value))
        if D(amt) < 0 or D(amt) > D(1_000_000):
            raise ValueError("refund_received out of range")
        scen = CScenario(id="lab", add=(("payments", {"id": "CRD-LAB", "type": "card_credit", "payment_id": pay["id"], "kind": "refund",
                                                     "amount": amt, "posted_at": index.case["as_of"]}),))
        desc = f"a refund credit of {_inr(amt)} posted to the card"
    elif kind == "cause" and ev and bk:
        cause = str(value).upper()
        if cause not in ("WEATHER", "OPERATIONAL", "TECHNICAL", "ATC_RESTRICTION"):
            raise ValueError("unsupported cause")
        corroborate = bool(change.get("corroborated"))
        dep = ts(bk["scheduled_departure"])
        adds = (("airport_ops", {"id": "OPS-LAB", "type": "ops_notice", "airport": bk["origin"], "category": cause,
                                 "valid_from": dep.isoformat(), "valid_to": dep.isoformat()}),) if corroborate else ()
        scen = CScenario(id="lab", patch={ev["id"]: {"cause_code": cause}}, add=adds)
        desc = f"cause {cause}{' corroborated by an airport notice' if corroborate else ' (uncorroborated)'}"
    elif kind == "alternate_accepted" and bk:
        scen = CScenario(id="lab", add=(("flight_ops", {"id": "ALT-LAB", "type": "alternate_offer", "booking_id": bk["id"],
                                                        "offered_departure": bk["scheduled_departure"], "accepted": bool(value)}),))
        desc = f"alternate flight {'accepted' if value else 'declined'}"
    elif kind == "drop_record" and value in index.records and index.system_of.get(value) != "claim":
        scen, desc = CScenario(id="lab", drop=(value,)), f"record {value} removed"
    elif kind == "stale_feed" and value in ("airline_pss", "flight_ops", "payments"):
        scen, desc = CScenario(id="lab", stale=(value,)), f"{value} snapshot treated as stale"
    else:
        raise ValueError("unsupported counterfactual; use notice_hours, refund_received, cause, alternate_accepted, drop_record or stale_feed")
    alt = decide(index, rulebook, scen, critic)
    before = {k: base[k] for k in ("status", "verdict", "action", "amount")} | {"delta": calc["delta"]}
    after = {k: alt[k] for k in ("status", "verdict", "action", "amount")} | {"delta": alt["calc"]["delta"]}
    steps_changed = [st["key"] for st in alt["calc"]["steps"] if st["value"] != (step_of(calc, st["key"]) or {}).get("value")]
    changed = (before["action"], before["amount"]) != (after["action"], after["amount"])
    return {"hypothetical": True, "change": desc, "before": before, "after": after, "changes_recommendation": changed,
            "steps_changed": steps_changed, "blockers_after": [b["detail"] for b in alt["calc"]["blockers"]],
            "summary": (f"With {desc}, the recommendation changes from {_label(base)} to {_label(alt)}." if changed
                        else f"With {desc}, the recommendation stays {_label(base)}.")}


# --------------------------------------------------------------------------- skeptic (independent stage)

def independent_recompute(index, rulebook, calc) -> dict:
    """A second, separately written path from raw records (notice, alternates, corroboration, slabs, credits).
    It shares no code with reclaim_policy.compute and must agree with it."""
    if calc["delta"] is None:
        return {"ran": False, "reason": "engine abstained"}
    bk, pay, ev = index.get(calc["booking_id"]), index.get(calc["payment_id"]), index.get(calc["event_id"])
    p_n = rulebook["by_id"]["IN-AIR-CANCEL-NOTICE"]["parameters"]
    p_x = rulebook["by_id"]["IN-AIR-EXTRAORDINARY"]["parameters"]
    dep = ts(bk["scheduled_departure"])
    notice_h = (dep - ts(ev["notified_at"])).total_seconds() / 3600
    alts = [a for a in index.of_type("alternate_offer") if a.get("booking_id") == bk["id"]]
    in_window = any(abs((ts(a["offered_departure"]) - dep).total_seconds()) <= p_n["alternate_window_minutes"] * 60
                    for a in alts if a.get("offered_departure"))
    accepted = any(a.get("accepted") is True for a in alts)
    w = timedelta(hours=p_x["corroboration_window_hours"])
    corroborated = ev.get("cause_code") in p_x["categories"] and any(
        n.get("airport") in (bk.get("origin"), bk.get("destination")) and n.get("category") in p_x["categories"]
        and ts(n["valid_from"]) <= dep + w and ts(n["valid_to"]) >= dep - w for n in index.of_type("ops_notice"))
    exempt = notice_h >= p_n["full_notice_hours"] or (notice_h >= p_n["min_notice_hours"] and in_window) or corroborated
    cap = next(D(c["cap"]) for c in rulebook["by_id"]["IN-AIR-CANCEL-COMP"]["parameters"]["slabs"]
               if c["max_block_minutes"] is None or int(bk["block_minutes"]) <= c["max_block_minutes"])
    refund_due = D(0) if accepted else D(pay["amount"])
    comp_due = D(0) if exempt else min(cap, D(bk["base_fare"]) + D(bk["fuel_charge"]))
    as_of = ts(index.case["as_of"])
    received = sum((D(c["amount"]) for c in index.of_type("card_credit") if c.get("payment_id") == pay["id"]
                    and ts(c["posted_at"]) <= as_of), D(0))
    if any(c.get("booking_id") == bk["id"] and c.get("consent") == "credit_shell" for c in index.of_type("passenger_consent")):
        received += sum((D(r["amount"]) for r in index.of_type("airline_refund") if r.get("booking_id") == bk["id"]
                         and r.get("mode") == "credit_shell"), D(0))
    owed = refund_due + comp_due - received
    agree = (fmt(owed), fmt(comp_due), fmt(refund_due)) == (calc["delta"], calc["compensation_due"], calc["refund_due"])
    return {"ran": True, "agree": agree, "refund_due": fmt(refund_due), "compensation_due": fmt(comp_due), "received": fmt(received),
            "owed": fmt(owed), "engine_owed": calc["delta"], "notice_hours": round(notice_h, 2), "payment": pay["id"]}


def _known_amounts(index, calc) -> set:
    known = set()
    for r in index.records.values():
        for k in ("amount", "base_fare", "fuel_charge", "taxes", "total_paid", "claimed_refund", "claimed_compensation"):
            if isinstance(r.get(k), str) and re.fullmatch(r"-?\d+(\.\d+)?", r[k]):
                known.add(D(r[k]))
    for st in calc["steps"]:
        for k in ("value", "refund", "compensation"):
            v = st.get(k)
            if isinstance(v, str) and re.fullmatch(r"-?\d+\.\d{2}", v):
                known.add(D(v))
    for k in ("due", "paid", "delta", "refund_due", "compensation_due", "refund_received"):
        if calc.get(k) is not None:
            known.add(abs(D(calc[k])))
    return known


def skeptic(index, rulebook, dec, agent, quarantined, source=None, requery=True) -> dict:
    """Tries to disprove the investigator: re-reads cited records through the source adapter, recomputes the
    money independently, challenges every agent citation and amount, lists missing evidence and what was
    not checked, and tests alternative hypotheses. Agreement between agents is never evidence."""
    calc, findings, unchecked = dec["calc"], [], []

    def f(fid, title, detail, cites, outcome, severity="medium", rule=None, kind=None):
        findings.append({"id": fid, "title": title, "detail": detail, "cites": cites, "outcome": outcome, "severity": severity,
                         "rule": rule, "kind": kind, "impact": None, "counterfactual": None})
    cited = sorted({c for st in calc["steps"] for c in st["cites"] if c in index.records and index.system_of.get(c) != "claim"})
    rechecks = []
    if requery and source is not None:  # 1. independent re-query through the adapter
        for rid in cited:
            fresh, meta = source.requery(index.case, rid)
            match = fresh is not None and compute_evidence_hash(fresh) == index.lineage[rid]["content_hash"]
            index.lineage[rid].update(rechecked=True, recheck_match=match, recheck_query_id=meta.get("query_id"),
                                      rechecked_at=meta.get("retrieved_at"))
            rechecks.append({"record_id": rid, "match": match, "query_id": meta.get("query_id")})
            if not match:
                f(f"SK-CX-DRIFT-{rid}", f"{rid} changed or vanished since the investigation read it",
                  "Re-query returned different content; the proof is stale and must be re-run.", [rid], "UNRESOLVED", "high", kind="DRIFT")
    else:
        unchecked.append("cited records were not independently re-queried (no source adapter in this run)")
    rec = independent_recompute(index, rulebook, calc)  # 2. independent money path
    if rec["ran"] and not rec["agree"]:
        f("SK-CX-RECOMPUTE", "Independent recomputation disagrees with the engine",
          f"independent owed {rec['owed']} vs engine {rec['engine_owed']}", [rec["payment"]], "UNRESOLVED", "high", kind="RECOMPUTE")
    known, owed = _known_amounts(index, calc), calc["delta"]
    for i, c in enumerate(agent.get("citations", []), 1):  # 3. challenge agent citations
        if c["status"] != "VERIFIED":
            sev = "high" if c["status"] in ("MISQUOTED", "WRONG_DOMAIN") else "medium"
            f(f"SK-CX-CITE-{i}", f"Agent citation {c['status'].lower().replace('_', ' ')}: {c['citation'][:80]}", c["reason"],
              [c["rule_id"]] if c.get("rule_id") else [], "CONFIRMED", sev, c.get("rule_id"), kind="CITATION")
    for i, a in enumerate(agent.get("amount_claims", []), 1):  # 4. challenge agent amounts
        if D(a["amount"]) not in known:
            f(f"SK-CX-AMOUNT-{i}", f"Agent states {_inr(a['amount'])}, which no record or computation supports",
              f"in {a['field']}: \"{a['context'].strip()}\"", [], "CONFIRMED", "high", kind="HALLUCINATION")
        elif owed is not None and a["field"] == "appeal_draft" and D(a["amount"]) != D(owed):
            f(f"SK-CX-DEMAND-{i}", f"Agent draft demands {_inr(a['amount'])}; the verified amount owed is {_inr(owed)}",
              "The filing uses the verified amount, not the draft's.", [], "CONFIRMED", "medium", kind="AMOUNT")
    for b in calc["blockers"]:  # 5. missing / unusable evidence
        f(f"SK-CX-MISSING-{b['code']}", b["detail"], "Decision withheld until this is resolved.", b["cites"], "UNRESOLVED", "high",
          kind="MISSING")
    for c in calc["conflicts"]:  # 6. contradictions, tested for materiality by replay
        if dec["materiality"].get(c["key"]):
            f(f"SK-CX-CONTRA-{c['code']}", c["detail"], "Contradictory source records change the amount owed.", c["cites"],
              "UNRESOLVED", "high", kind="CONTRADICTION")
        else:
            f(f"SK-CX-CONTRA-{c['code']}", c["detail"], "Checked: either record leaves the amount owed unchanged.",
              c["cites"], "RULED_OUT", "low", kind="CONTRADICTION")
    for ex in (step_of(calc, "received") or {}).get("excluded", []):
        f(f"SK-CX-SHELL-{ex['id']}", f"{ex['id']} is a credit shell without passenger consent", ex["reason"], [ex["id"]], "CONFIRMED",
          "medium", "IN-AIR-CREDIT-SHELL", kind="RULE")
    ext = step_of(calc, "extraordinary")
    if ext and ext["value"] == "EXEMPT":
        f("SK-CX-EXTRA", "Compensation excused by corroborated extraordinary circumstances", ext["formula"], ext["cites"], "CONFIRMED",
          "medium", "IN-AIR-EXTRAORDINARY", kind="RULE")
    for q in quarantined:  # 7. injection quarantine
        f(f"SK-CX-INJ-{q['record_id']}", f"Embedded instruction in {q['record_id']}.{q['field']} quarantined",
          f"Scout injection check ({', '.join(q['kinds'])}) flagged this text. It is excluded from model context and the action is "
          "escalated to controller approval.", [q["record_id"]], "UNRESOLVED", "high", "SCOUT-GUARD", kind="INJECTION")
    agree = [a for a in agent.get("amount_claims", []) if a["field"] == "appeal_draft" and owed is not None and D(a["amount"]) == D(owed)]
    supported = owed is not None and all(st["cites"] for st in calc["steps"] if st["key"] in ("payment", "cancellation", "compensation", "received"))
    agreement = {"agent_amount_matches_engine": bool(agree), "independently_supported": supported,
                 "note": ("The RECLAIM agent and the engine agree, but the decision rests on the cited records, re-queried and "
                          "recomputed independently - not on the agreement." if agree else
                          "No agent agreement is relied on; the decision rests on the cited records.")}
    if agree and not supported:  # 8. agreement is not evidence
        f("SK-CX-AGREEMENT", "Agents agree but the claim lacks independent record support", agreement["note"], [], "UNRESOLVED", "high",
          kind="AGREEMENT")
    if not agent.get("available"):
        unchecked.append("RECLAIM agent analysis unavailable: no agent citations or drafts were challenged")
    if not index.doc_fact("notified_at"):
        unchecked.append("no claimant document states the notification time; the carrier's log is unchallenged on notice")
    if not index.case["sources"]["airport_ops"]["records"]:
        unchecked.append("no airport operations notices were available to test an extraordinary-circumstances defence")
    if not (index.case.get("reclaim") or {}).get("case_id"):
        unchecked.append("case not linked to a RECLAIM case: documents are local fixtures, not the RECLAIM vault")
    against = [x for x in findings if x["outcome"] == "UNRESOLVED"] or [x for x in findings if x["severity"] == "high"] or findings
    return {"findings": findings, "strongest": against[0]["id"] if against else None, "rechecks": rechecks,
            "independent_recompute": rec, "agreement": agreement, "unchecked": unchecked}


# --------------------------------------------------------------------------- hypotheses

def hypotheses(index, dec, sk, quarantined) -> list[dict]:
    calc, status = dec["calc"], dec["status"]
    st = {s["key"]: s for s in calc["steps"]}
    blockers = {b["code"] for b in calc["blockers"]}
    contra = {c["key"] for c in calc["conflicts"] if dec["materiality"].get(c["key"])}
    out = []

    def h(hid, statement, status_, supporting, opposing, checks, uncertainty, kind):
        out.append({"id": hid, "kind": kind, "statement": statement, "status": status_, "supporting": sorted(set(supporting)),
                    "opposing": sorted(set(opposing)), "required_checks": checks, "uncertainty": uncertainty})

    def chk(name, passed, detail=""):
        return {"check": name, "passed": bool(passed), "detail": detail}
    ident = st.get("identity", {}).get("value")
    owed = calc["delta"]
    checks = [chk("claimant linked to booked passenger", ident == "RESOLVED", ident or "not reached"),
              chk("payment captured and consistent", "payment" in st and "payment" not in contra),
              chk("cancellation recorded by the carrier", "cancellation" in st),
              chk("money received recomputed independently", sk["independent_recompute"].get("agree", False)),
              chk("cited records re-queried unchanged", bool(sk["rechecks"]) and all(r["match"] for r in sk["rechecks"]),
                  f"{sum(r['match'] for r in sk['rechecks'])}/{len(sk['rechecks'])}"),
              chk("no material contradiction", not contra, ", ".join(sorted(contra)))]
    if quarantined or "DOMAIN_UNSUPPORTED" in blockers or ident == "AMBIGUOUS":
        s1 = "NEEDS_HUMAN_REVIEW"
    elif status == "NEEDS_EVIDENCE":
        s1 = "INSUFFICIENT_EVIDENCE"
    elif status in ("DISPUTED", "REJECTED"):
        s1 = "CONTRADICTORY"
    else:
        s1 = "SUPPORTED" if D(owed) > 0 else "REFUTED"
    supp = [c for k in ("payment", "cancellation", "compensation", "received") for c in st.get(k, {}).get("cites", [])]
    opp = [x for cf in calc["conflicts"] for x in cf["cites"]] + [e["id"] for e in st.get("received", {}).get("excluded", [])]
    h("H1", f"The carrier owes the claimant {_inr(owed)}" + (f" (refund {_inr(calc['refund_due'])} + compensation "
                                                              f"{_inr(calc['compensation_due'])} - received {_inr(calc['paid'])})"
                                                              if owed is not None else " (amount not yet determinable)"),
      s1, supp, opp, checks, {"SUPPORTED": "Low: every input was re-read and recomputed independently.",
                              "REFUTED": "Low: the records show nothing outstanding.",
                              "INSUFFICIENT_EVIDENCE": "High: " + "; ".join(b["detail"] for b in calc["blockers"]),
                              "CONTRADICTORY": "High: sources disagree on a fact that changes the amount.",
                              "NEEDS_HUMAN_REVIEW": "Needs a person: quarantined content, an unsupported domain or an unclear identity."}[s1],
      "primary")
    if "received" in st:
        rcv = st["received"]
        paid_back = D(rcv["value"]) > 0
        due_refund = D(calc.get("refund_due") or 0)
        s2 = ("CONTRADICTORY" if "airline_refund" in contra else
              "SUPPORTED" if paid_back and D(rcv.get("refund", "0")) >= due_refund > 0 else "REFUTED")
        h("H2", "The refund has already been paid", s2, rcv["cites"] if paid_back else [],
          [e["id"] for e in rcv.get("excluded", [])] + ([calc["payment_id"]] if not paid_back else []),
          [chk("card ledger fresh", not index.is_stale("payments")),
           chk("credits matched to the original payment", True, f"{len(rcv['cites'])} record(s)")],
          "Card-network credits are authoritative for receipt; carrier-side refund claims are cross-checked, not trusted.", "alternative")
    if "extraordinary" in st:
        ext = st["extraordinary"]
        s3 = "CONTRADICTORY" if "extraordinary" in contra else "SUPPORTED" if ext["value"] == "EXEMPT" else "REFUTED"
        h("H3", "Compensation is excused by extraordinary circumstances", s3, ext["cites"] if ext["value"] == "EXEMPT" else [],
          [] if ext["value"] == "EXEMPT" else ext["cites"],
          [chk("carrier asserts an extraordinary cause", "operational" not in ext["formula"]),
           chk("airport notice corroborates", "corroborated by" in ext["formula"])],
          "A carrier's own cause code is not enough; an independent airport notice must corroborate it.", "alternative")
    if "alternate" in st:
        alt = st["alternate"]
        acc = alt["value"] == "ACCEPTED"
        h("H4", "The claimant accepted an alternate flight", "SUPPORTED" if acc else "REFUTED", alt["cites"] if acc else [],
          [] if acc else alt["cites"], [chk("acceptance recorded by flight operations", acc)],
          "Only an acceptance recorded by the carrier counts.", "alternative")
    if "notice" in st:
        p = index.rulebook["by_id"]["IN-AIR-CANCEL-NOTICE"]["parameters"]
        nh = float(st["notice"]["value"])
        adequate = nh >= p["full_notice_hours"] or (nh >= p["min_notice_hours"] and st.get("alternate", {}).get("value") != "NONE_IN_WINDOW")
        h("H5", "Passengers received adequate notice (no compensation due)",
          "CONTRADICTORY" if "notice" in contra else "SUPPORTED" if adequate else "REFUTED", st["notice"]["cites"], [],
          [chk("notice >= 2 weeks, or >= 24h with an alternate within 2h", adequate, f"{nh:.1f}h")],
          "Notice comes from the carrier's notification log; a contradicting claimant document makes it contradictory.", "alternative")
    if ident:
        h("H6", "The claimant is the booked passenger", {"RESOLVED": "SUPPORTED", "AMBIGUOUS": "NEEDS_HUMAN_REVIEW",
                                                          "MISMATCH": "REFUTED"}[ident], st["identity"]["cites"], [],
          [chk("name similarity >= 0.85", ident == "RESOLVED", st["identity"]["formula"])],
          "Names are compared after normalisation; anything below the auto-link threshold goes to a person.", "identity")
    return out


# --------------------------------------------------------------------------- verifier, planner, validator

def verifier(index, rulebook, dec, sk, wm_check) -> dict:
    calc, inv = dec["calc"], []

    def check(name, ok, detail=""):
        inv.append({"invariant": name, "passed": bool(ok), "detail": detail})
    known_rules = set(rulebook["by_id"]) | {"IDENTITY", "BOOKING", "PAYMENT"}
    missing = [c for s in calc["steps"] for c in s["cites"] if not index.exists(c)]
    check("every calculation citation resolves to a real record or document", not missing, ", ".join(missing))
    check("every step cites a rule from the versioned rulebook", all(s["rule"] in known_rules for s in calc["steps"]))
    if calc["delta"] is not None:
        check("due = refund_due + compensation_due", D(calc["due"]) == D(calc["refund_due"]) + D(calc["compensation_due"]))
        check("owed = due - received", D(calc["delta"]) == D(calc["due"]) - D(calc["paid"]))
        bk = index.get(calc["booking_id"])
        check("compensation <= basic fare + fuel charge", D(calc["compensation_due"]) <= D(bk["base_fare"]) + D(bk["fuel_charge"]))
        if sk["independent_recompute"].get("ran"):
            check("independent recomputation agrees with the engine", sk["independent_recompute"]["agree"],
                  f"independent {sk['independent_recompute']['owed']} vs engine {calc['delta']}")
        money = [s["value"] for s in calc["steps"] if s["key"] in ("booking", "payment", "refund_due", "compensation", "received", "due", "paid")]
        check("monetary values are exact 2-dp decimal strings", all(re.fullmatch(r"-?\d+\.\d{2}", v) for v in money))
    if sk["rechecks"]:
        check("cited records re-read unchanged through the source adapter", all(r["match"] for r in sk["rechecks"]),
              f"{sum(r['match'] for r in sk['rechecks'])}/{len(sk['rechecks'])} matched")
    if wm_check:
        inv.append(wm_check)
    failed = [i for i in inv if not i["passed"]]
    return {"invariants": inv, "proof_status": "REJECTED" if failed else dec["status"], "failed": [i["invariant"] for i in failed]}


def world_model_cross_check(world, ids, index, calc):
    """The card credits the World Model's as-of view links to the payment must be exactly the ones counted."""
    if calc["delta"] is None or calc["payment_id"] not in ids:
        return None
    engine = {c for c in step_of(calc, "received")["cites"] if (index.get(c) or {}).get("type") == "card_credit"}
    at = ts(index.case["as_of"]).strftime("%Y-%m-%dT%H:%M:%S.999Z")
    world_set = {e["id"].split(":")[-1] for e in world.neighbors_of(ids[calc["payment_id"]], via="credits", at=at)}
    return {"invariant": "Meterless World Model as-of view matches the card credits the engine counted", "passed": engine == world_set,
            "detail": f"world={sorted(world_set)} engine={sorted(engine)}"}


def grievance_letter(case, calc, citations) -> str:
    d, verified = case["dispute"], [c for c in citations if c["status"] == "VERIFIED"]
    basis = "; ".join(sorted({f"{c['instrument']} - {c['provision']}" for c in verified})) or \
        "rulebook provisions IN-AIR-CANCEL-REFUND and IN-AIR-CANCEL-COMP (paraphrased; verify against the official text)"
    return "\n".join([f"To: Grievance Officer, {case['institution_name']}",
                      f"Re: Cancellation of flight {d.get('flight_no')} (PNR {d.get('booking_ref')}) - claim {d['id']}",
                      f"Amount outstanding: {_inr(calc['delta'])} (refund {_inr(calc['refund_due'])} + compensation "
                      f"{_inr(calc['compensation_due'])} - received {_inr(calc['paid'])}).",
                      f"Refund deadline under the payment-mode timeline: {calc.get('deadline') or 'not determinable'}"
                      + (" (overdue)." if calc.get("overdue") else "."),
                      f"Basis: {basis}.",
                      "This is a sandbox submission prepared for human review. No real filing has been made."])


def planner(index, rulebook, dec, verdict, status, fingerprint, run_id, agent, quarantined) -> dict:
    case, calc = index.case, dec["calc"]
    typ, amount = plan_type(status, calc)
    perm = "controller" if amount and D(amount) > D(rulebook["approval_limits"]["finance_approver"]) else "finance_approver"
    breakdown, letter = None, None
    if typ == "FILE_GRIEVANCE":
        breakdown = {"refund_outstanding": fmt(max(D(0), D(calc["refund_due"]) - D(calc["refund_received"]))),
                     "compensation_outstanding": fmt(max(D(0), D(calc["compensation_due"]) - D(calc["compensation_received"])))}
        justification = f"Verified: {_inr(calc['due'])} due, {_inr(calc['paid'])} received; outstanding {_inr(amount)}."
        expected = f"Sandbox grievance submitted to {case['institution_name']} for {_inr(amount)}; no money moves."
        letter = grievance_letter(case, calc, agent.get("citations", []))
    else:
        justification = {"REQUEST_EVIDENCE": "; ".join(b["detail"] for b in calc["blockers"]) or "Evidence incomplete.",
                         "ESCALATE_FOR_REVIEW": "; ".join(c["detail"] for c in calc["conflicts"] if dec["materiality"].get(c["key"]))
                         or "; ".join(b["detail"] for b in calc["blockers"]) or "Verification failed; a person must review.",
                         "CLOSE_NO_ACTION": f"Nothing outstanding: {_inr(calc.get('due'))} due, {_inr(calc.get('paid'))} received."}[typ]
        expected = {"REQUEST_EVIDENCE": "Evidence request sent to the claimant and source owners (sandbox).",
                    "ESCALATE_FOR_REVIEW": "Case routed to a human adjudicator; nothing is filed.",
                    "CLOSE_NO_ACTION": "Claimant receives the reconciliation; nothing is filed."}[typ]
    action = {"type": typ, "case_id": case["case_id"], "tenant_id": case.get("tenant_id"), "amount": amount, "currency": "INR",
              "breakdown": breakdown, "institution": case.get("institution_name"), "justification": justification,
              "affected_records": sorted({c for s in calc["steps"] for c in s["cites"]} or {case["dispute"]["id"]}),
              "expected_result": expected,
              "preconditions": {"source_fingerprint": fingerprint, "proof_status": status, "expected_received_before": calc.get("paid"),
                                "expected_due": calc.get("due")},
              "required_permission": perm, "run_id": run_id, "verdict": verdict,
              "idempotency_key": "IDK-" + sha([case["case_id"], typ, amount, fingerprint])[:16], "simulated": True,
              "execution_mode": "sandbox", "payload": {"letter": letter, "letter_hash": compute_evidence_hash(letter) if letter else None,
                                                       "deadline": calc.get("deadline"), "overdue": calc.get("overdue")}}
    if quarantined:
        action.update(escalated=True, required_permission="controller")
        action["justification"] += f" Escalated: {len(quarantined)} source item(s) contained embedded instructions."
    return action


def final_validator(index, rulebook, status, calc, narrative_claims, action, agent) -> dict:
    errors, unsupported, accepted = [], [], []
    known_ids = set(index.records) | set(index.documents) | set(rulebook["by_id"])
    known_amounts = _known_amounts(index, calc)
    for c in narrative_claims:
        bad_cite = [x for x in c["cites"] if x not in known_ids]
        bad_amt = [a for a in (D(m.replace(",", "")) for m in AMOUNT_RE.findall(c["text"])) if a not in known_amounts]
        if not c["cites"] or bad_cite or bad_amt:
            unsupported.append({**c, "reason": "no citation" if not c["cites"] else f"unknown ids {bad_cite}" if bad_cite
                                else f"unverifiable amounts {[str(a) for a in bad_amt]}"})
        else:
            accepted.append(c)
    if action["type"] not in ACTION_TYPES:
        errors.append(f"action {action['type']} not in allowlist")
    if action["type"] == "FILE_GRIEVANCE":
        if status != "VERIFIED":
            errors.append("grievance proposed without VERIFIED proof")
        if D(action["amount"]) != D(calc["delta"]) or D(action["amount"]) <= 0:
            errors.append("grievance amount does not equal the verified positive amount outstanding")
        if action["payload"]["letter"] and any(c["citation"][:60] in action["payload"]["letter"]
                                               for c in agent.get("citations", []) if not c["verified"]):
            errors.append("unverified citation leaked into the filing")
    return {"passed": not errors, "errors": errors, "unsupported_claims": unsupported, "accepted_narrative": accepted}


# --------------------------------------------------------------------------- explanation

def explanation(index, dec, verdict, status, sk, hyps, cfs, attr, narrative) -> dict:
    calc, st = dec["calc"], {s["key"]: s for s in dec["calc"]["steps"]}
    because = []
    for key, text in (("cancellation", lambda s: f"The carrier cancelled the flight ({s['formula']})"),
                      ("notice", lambda s: f"Passengers were notified {float(s['value']):.1f} hours before departure"),
                      ("alternate", lambda s: f"Alternate flight: {s['value'].replace('_', ' ').lower()}"),
                      ("refund_due", lambda s: f"Refund entitlement {_inr(s['value'])} ({s['formula']})"),
                      ("extraordinary", lambda s: f"Extraordinary-circumstances test: {s['value'].replace('_', ' ').lower()} ({s['formula']})"),
                      ("compensation", lambda s: f"Compensation {_inr(s['value'])}: {s['formula']}"),
                      ("received", lambda s: f"Received so far {_inr(s['value'])} ({s['formula']})"),
                      ("deadline", lambda s: f"Refund deadline {s['value']}" + (" - overdue" if s.get("overdue") else ""))):
        if key in st:
            because.append({"step": key, "fact": text(st[key]), "rule": st[key]["rule"], "records": st[key]["cites"]})
    action, why_not = dec["action"], []
    if action == "FILE_GRIEVANCE":
        why_not.append({"alternative": "CLOSE_NO_ACTION", "because": f"{_inr(calc['delta'])} is still outstanding on the card ledger "
                        f"({', '.join(st['received']['cites'])})."})
        why_not.append({"alternative": "ESCALATE_FOR_REVIEW", "because": "No material contradiction survived the skeptic ("
                        + (", ".join(x["id"] for x in sk["findings"] if x["outcome"] == "RULED_OUT") or "none were found") + ")."})
    elif action == "CLOSE_NO_ACTION":
        why_not.append({"alternative": "FILE_GRIEVANCE", "because": f"Nothing is outstanding: due {_inr(calc['due'])}, received {_inr(calc['paid'])}."})
    elif action == "ESCALATE_FOR_REVIEW":
        why_not.append({"alternative": "FILE_GRIEVANCE", "because": "A material contradiction, failed check or unsupported domain means "
                        "the amount cannot be verified; filing would rest on an unverified premise."})
    else:
        why_not.append({"alternative": "FILE_GRIEVANCE", "because": "Required evidence is missing or unusable: "
                        + "; ".join(b["detail"] for b in calc["blockers"])})
    strongest = next((x for x in sk["findings"] if x["id"] == sk["strongest"]), None)
    return {"decision": {"action": action, "amount": dec["amount"], "proof_status": status, "verdict": verdict},
            "because": because, "why_not": why_not,
            "strongest_counterargument": ({"id": strongest["id"], "title": strongest["title"], "detail": strongest["detail"]}
                                          if strongest else None),
            "pivotal_evidence": [a for a in attr if a["pivotal"]], "unchecked": sk["unchecked"],
            "next_evidence": [{"evidence": c["title"], "question": c["question"], "would_change_to": c["summary"]}
                              for c in cfs if c["changes_recommendation"]][:4],
            "hypotheses": [{k: h[k] for k in ("id", "statement", "status")} for h in hyps], "narrative": narrative}


# --------------------------------------------------------------------------- orchestration

def investigate_consumer(case: dict, rulebook: dict, source=None, model: ModelClient | None = None, memory=None,
                         options: dict | None = None) -> dict:
    """options (ablations; all True in the product):
         critic       skeptic findings + conflict materiality + citation/amount challenge
         world_model  Meterless World Model ingest, cross-check and model context
         scout        Meterless Scout quarantine of embedded instructions in documents and records
         memory       Meterless H-MEM precedent recall (never changes the decision)
         requery      independent re-query of cited records through the source adapter"""
    opt = {"critic": True, "world_model": True, "scout": True, "memory": True, "requery": True, **(options or {})}
    t0 = time.monotonic()
    model = model or ModelClient()
    trace, mark = [], [time.monotonic()]

    def stage(key, agent_name, summary, **extra):
        now = time.monotonic()
        trace.append({"stage": key, "agent": agent_name, "ms": round((now - mark[0]) * 1000, 3), "summary": summary, **extra})
        mark[0] = now

    dq = data_quality(case)
    if dq["excluded"]:
        case = without(case, dq["excluded"])
    index = ConsumerEvidenceIndex(case, rulebook)
    fingerprint = consumer_fingerprint(case)
    agent = normalize_agent_run(case.get("agent_run"), rulebook, case.get("domain"))
    run_id = "CRUN-" + sha([fingerprint, ENGINE_VERSION, rulebook["rulebook_version"], compute_evidence_hash(case.get("agent_run"))])[:12]
    stage("intake", "RECLAIM intake + evidence bridge",
          f"claim {case['dispute']['id']} · {len(index.records) - 1} institution record(s) · {len(index.documents)} document(s) · "
          f"{len(index.doc_facts)} document fact(s) · data quality "
          + ("passed" if dq["passed"] else f"excluded {len(dq['excluded'])} record(s)"))
    stage("agents", "RECLAIM specialist agents",
          (f"{agent['provenance']} run · {len(agent['citations'])} citation(s) · {len(agent['amount_claims'])} amount claim(s) to verify"
           if agent["available"] else "no RECLAIM agent run available for this case"))
    stage("federation", "Zetaris federation" if getattr(source, "zetaris", None) else "Source adapter (local fixtures)",
          " · ".join(f"{q['system']}: {q.get('rows', 0)} row(s) [{q.get('provenance')}]" for q in case.get("queries", [])) or "no queries")

    world = wm.WorldModel(namespace=f"consumer/{case['case_id']}")
    wm_ingest = ingest_consumer_case(world, case, run_id) if opt["world_model"] else \
        {"ids": {}, "state_hash": None, "entities": 0, "relationships": 0}
    from .integrations import record, record_world_model_ingest
    if opt["world_model"]:
        record_world_model_ingest()
    stage("world_model", "Meterless World Model", f"{wm_ingest['entities']} entities · {wm_ingest['relationships']} bitemporal edges"
          if opt["world_model"] else "disabled (ablation)")

    dec = decide(index, rulebook, None, opt["critic"])
    calc = dec["calc"]
    stage("policy", "Deterministic policy engine", f"due {calc['due']} · received {calc['paid']} · owed {calc['delta']} · "
          f"{len(calc['blockers'])} blocker(s) · {len(calc['conflicts'])} conflict(s)", rulebook=rulebook["rulebook_version"])
    cfs = replay(index, rulebook, dec, opt["critic"])
    attr = attribution(index, rulebook, dec, opt["critic"])
    stage("counterfactual", "Counterfactual replay", f"{len(cfs)} scenarios ({sum(c['changes_recommendation'] for c in cfs)} change the "
          f"recommendation) · {sum(a['pivotal'] for a in attr)}/{len(attr)} cited records pivotal")

    t_sc = time.monotonic()
    quarantined = []
    if opt["scout"]:
        quarantined = scan_records(case)
        for doc in case.get("documents", []):
            res = injection_check(doc.get("text", ""))
            if res["detected"]:
                quarantined.append({"record_id": doc["id"], "system": "documents", "field": "text", **res})
        record("scout", (time.monotonic() - t_sc) * 1000, quarantined_records=len(quarantined))
    stage("guard", "Meterless Scout guard", f"{len(quarantined)} item(s) quarantined" if opt["scout"] else "disabled (ablation)")

    if opt["critic"]:
        sk = skeptic(index, rulebook, dec, agent, quarantined, source, opt["requery"])
    else:
        sk = {"findings": [], "strongest": None, "rechecks": [], "independent_recompute": {"ran": False, "reason": "skeptic disabled"},
              "agreement": {"note": "skeptic disabled (ablation)"}, "unchecked": ["skeptic disabled (ablation)"]}
    rec = sk["independent_recompute"]
    stage("adversarial", "Independent skeptic", f"{len(sk['findings'])} falsification finding(s) · "
          f"{sum(r['match'] for r in sk['rechecks'])}/{len(sk['rechecks'])} records re-queried unchanged · recompute "
          + ("agrees" if rec.get("agree") else "n/a" if not rec.get("ran") else "DISAGREES"))
    wm_check = world_model_cross_check(world, wm_ingest["ids"], index, calc) if opt["world_model"] else None
    ver = verifier(index, rulebook, dec, sk, wm_check)
    status = ver["proof_status"]
    verdict = verdict_for(status, calc, claimed_total(case))
    action = planner(index, rulebook, dec, verdict, status, fingerprint, run_id, agent, quarantined)
    hyps = hypotheses(index, {**dec, "status": status}, sk, quarantined)
    stage("verify", "Invariant verifier", f"{sum(i['passed'] for i in ver['invariants'])}/{len(ver['invariants'])} invariants · status {status}")

    quarantined_ids = {q["record_id"] for q in quarantined}
    verified_cites = [{k: c[k] for k in ("rule_id", "instrument", "provision", "rule_text")} for c in agent.get("citations", []) if c["verified"]]
    facts = {"status": status, "verdict": verdict, "owed": calc["delta"], "due": calc["due"], "received": calc["paid"],
             "action": action["type"], "steps": [{k: s[k] for k in ("label", "value", "rule", "cites")} for s in calc["steps"]],
             "verified_citations": verified_cites,
             "world_model_context": [c for c in (wm.context_for(world, wm_ingest["ids"][calc["booking_id"]])
                                                 if opt["world_model"] and calc.get("booking_id") in wm_ingest["ids"] else [])
                                     if c["id"] not in quarantined_ids]}
    base_expl = explanation(index, {**dec, "action": action["type"], "amount": action["amount"]}, verdict, status, sk, hyps, cfs, attr, [])
    fallback = [{"text": b["fact"] + ".", "cites": b["records"]} for b in base_expl["because"] if b["records"]][:4]
    narrative, _ = model.narrate("explain_resolution", facts, fallback, system=NARRATOR_SYSTEM)
    strongest = next((x for x in sk["findings"] if x["id"] == sk["strongest"]), None)
    sk_claims = [{"text": f"{strongest['title']}. {strongest['detail']}", "cites": strongest["cites"] or [case["dispute"]["id"]]}] if strongest else []
    sk_text, _ = model.narrate("strongest_counterargument",
                               {"findings": [{k: x[k] for k in ("title", "detail", "cites", "outcome")} for x in sk["findings"]]},
                               sk_claims, system=NARRATOR_SYSTEM)
    validation = final_validator(index, rulebook, status, calc, narrative + sk_text, action, agent)
    if not validation["passed"]:
        action = {**action, "type": "ESCALATE_FOR_REVIEW", "amount": None, "blocked_by_validator": validation["errors"]}
    stage("decision", "Resolution planner + final validator", f"{action['type']} ({action['required_permission']} approval); validator "
          f"{'passed' if validation['passed'] else 'FAILED'}; {len(validation['unsupported_claims'])} unsupported claim(s) dropped; "
          f"model: {', '.join(m['status'] for m in model.calls) or 'none'}")

    expl = {**base_expl, "decision": {"action": action["type"], "amount": action["amount"], "proof_status": status, "verdict": verdict},
            "narrative": validation["accepted_narrative"]}
    mats = dec["materiality"]
    contra = contradictions(index, calc, mats)
    claims = []
    for key, label in (("payment", "Amount the claimant paid"), ("refund_due", "Refund entitlement"),
                       ("compensation", "Compensation entitlement"), ("received", "Money already received"), ("due", "Total due")):
        s = step_of(calc, key)
        if s:
            claims.append({"id": f"CLM-{key.upper()}", "statement": f"{label}: {_inr(s['value'])}", "rule": s["rule"],
                           "verification_method": ("deterministic recomputation + independent re-query" if opt["critic"]
                                                   else "deterministic computation"),
                           "supporting": s["cites"],
                           "contradicting": sorted({r for c in contra if c["material"] for r in c["records"] if r in s["cites"]}),
                           "lineage": [index.lineage[c] for c in s["cites"] if c in index.lineage]})
    core = {"case_id": case["case_id"], "tenant_id": case.get("tenant_id"), "run_id": run_id, "engine_version": ENGINE_VERSION,
            "rulebook_version": rulebook["rulebook_version"], "source_fingerprint": fingerprint, "proof_status": status,
            "verdict": verdict, "calculation": calc, "counterfactuals": cfs, "proposed_action": action,
            "world_model_state_hash": wm_ingest["state_hash"]}
    result = {
        **core, "proof_hash": sha(core), "title": case.get("title"), "domain": case.get("domain"), "jurisdiction": case.get("jurisdiction"),
        "institution_name": case.get("institution_name"), "tags": case.get("tags", []), "dispute": case["dispute"],
        "documents": [{k: d.get(k) for k in ("id", "kind", "title", "provenance", "reclaim_document_id")} for d in case.get("documents", [])],
        "doc_facts": index.doc_facts, "agent": agent, "hypotheses": hyps, "skeptic": sk, "verification": ver,
        "materiality": mats, "contradictions": contra, "attribution": attr, "claims": claims, "explanation": expl,
        "lineage": sorted(index.lineage.values(), key=lambda x: (x["system"], x["record_id"])), "data_quality": dq,
        "validation": validation, "narrative": validation["accepted_narrative"],
        "security": {"quarantined": quarantined, "escalated": bool(quarantined)}, "options": opt, "trace": trace,
        "sources_meta": {"provenance": case.get("provenance", {}), "feeds": case.get("feeds", {}), "queries": case.get("queries", []),
                         "late_events": case.get("late_events", [])},
        "reclaim": case.get("reclaim") or {},
        "telemetry": {"latency_ms": round((time.monotonic() - t0) * 1000, 2), "model_calls": model.calls, "model_identity": model.identity},
        "world_model": {"engine": wm.ENGINE, "namespace": world.namespace, "state_hash": wm_ingest["state_hash"],
                        "entities": wm_ingest["entities"], "relationships": wm_ingest["relationships"], "events": len(world.events),
                        "cross_check": wm_check, "audit_tail": world.audit()[-5:]},
        "_world": world,
    }
    precedents = {"patterns": [], "precedents": [], "trace": None}
    if memory is not None and opt["memory"]:
        try:
            precedents = memory.recall(result, tenant=case.get("tenant_id"), consumer=True)
        except Exception as exc:  # memory informs reviewers; its failure never blocks or changes a decision
            precedents = {"patterns": [], "precedents": [], "trace": None, "error": type(exc).__name__}
    result["precedents"] = precedents
    stage("memory", "Meterless H-MEM", f"{len(precedents['precedents'])} verified precedent(s) recalled (informational only)"
          if opt["memory"] and memory is not None else "not consulted")
    return result
