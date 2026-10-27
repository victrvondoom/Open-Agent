"""Consumer evidence layer: lineage, freshness, data quality, document facts, contradictions.

Turns a federated consumer case (claim + RECLAIM documents + institution records) into an index
where every record carries its lineage: source system, source record id, query id, retrieval
time, content hash, feed freshness and whether the skeptic independently re-checked it.
RECLAIM agent output is normalised into claims to verify (citations, amounts); it is never evidence.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from .money import D, fmt
from .reclaim_policy import ts, verify_citation
from . import world_model as wm

MONEY_FIELDS = ("amount", "base_fare", "fuel_charge", "taxes", "total_paid")
TIME_FIELDS = ("scheduled_departure", "captured_at", "posted_at", "notified_at", "offered_departure", "processed_at",
               "valid_from", "valid_to")
REQUIRED = {
    "booking": ("booking_ref", "passenger_name", "flight_no", "scheduled_departure", "block_minutes", "base_fare",
                "fuel_charge", "taxes", "total_paid"),
    "card_payment": ("booking_id", "amount"),
    "card_credit": ("payment_id", "amount", "posted_at"),
    "flight_event": ("booking_id", "event"),
    "alternate_offer": ("booking_id",),
    "airline_refund": ("booking_id", "amount", "mode", "status", "processed_at"),
    "passenger_consent": ("booking_id", "consent"),
    "ops_notice": ("airport", "category", "valid_from", "valid_to"),
}
REFS = (("booking_id", "booking"), ("payment_id", "card_payment"))
CONFLICT_KIND = {"PAYMENT_AMOUNT_MISMATCH": "AMOUNT", "FARE_COMPONENTS_MISMATCH": "AMOUNT", "NOTICE_TIME_CONFLICT": "TIME",
                 "AIRLINE_REFUND_UNCONFIRMED": "STATUS", "FLIGHT_STATUS_CONFLICT": "STATUS",
                 "EXTRAORDINARY_UNCORROBORATED": "CAUSE", "DUPLICATE_BOOKING": "IDENTITY"}
INR_RE = re.compile(r"(?:\b(?:INR|Rs\.?)|₹)\s*([\d,]+(?:\.\d{1,2})?)", re.I)
IST = timezone(timedelta(hours=5, minutes=30))


def compute_evidence_hash(data) -> str:
    """Deterministic SHA-256 fingerprint (first 16 hex) of any JSON-serialisable value."""
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- data quality (fail closed)

def data_quality(case: dict) -> dict:
    """Per-system checks on federated rows. Records with malformed money/time or missing required fields
    are excluded from analysis (never repaired); dangling references are reported."""
    issues, excluded, seen = [], set(), {}
    all_ids = {r.get("id"): r.get("type") for blk in case["sources"].values() for r in blk["records"]}
    for system, blk in case["sources"].items():
        for r in blk["records"]:
            rid = r.get("id")
            if not rid:
                issues.append({"system": system, "record_id": None, "check": "has_id", "severity": "error"})
                continue
            if rid in seen:
                issues.append({"system": system, "record_id": rid, "check": "unique_id", "severity": "error",
                               "detail": f"also in {seen[rid]}"})
                excluded.add(rid)
            seen[rid] = system
            for f in REQUIRED.get(r.get("type"), ()):
                if r.get(f) in (None, ""):
                    issues.append({"system": system, "record_id": rid, "check": f"required:{f}", "severity": "error"})
                    excluded.add(rid)
            for f in MONEY_FIELDS:
                v = r.get(f)
                if v is not None and (isinstance(v, (float, bool)) or not re.fullmatch(r"-?\d+\.\d{2}", str(v))):
                    issues.append({"system": system, "record_id": rid, "check": f"exact_decimal:{f}", "severity": "error"})
                    excluded.add(rid)
            for f in TIME_FIELDS:
                if r.get(f) is None:
                    continue
                try:
                    ts(r[f])
                except (TypeError, ValueError):
                    issues.append({"system": system, "record_id": rid, "check": f"timestamp:{f}", "severity": "error"})
                    excluded.add(rid)
            for field, rtype in REFS:
                if r.get(field) and all_ids.get(r[field]) != rtype:
                    issues.append({"system": system, "record_id": rid, "check": f"reference:{field}", "severity": "warning",
                                   "detail": f"{r[field]} not found among federated {rtype} records"})
    per_system = {s: {"rows": len(b["records"]), "errors": sum(1 for i in issues if i["system"] == s and i["severity"] == "error"),
                      "warnings": sum(1 for i in issues if i["system"] == s and i["severity"] == "warning")}
                  for s, b in case["sources"].items()}
    return {"passed": not excluded, "issues": issues, "excluded": sorted(excluded), "per_system": per_system}


def without(case: dict, record_ids) -> dict:
    ids = set(record_ids)
    return {**case, "sources": {s: {**b, "records": [r for r in b["records"] if r["id"] not in ids]} for s, b in case["sources"].items()}}


# --------------------------------------------------------------------------- documents

def extract_doc_facts(documents: list[dict]) -> list[dict]:
    """Deterministic, span-anchored extraction (regex/v1). Facts are claimant-side evidence and are
    cross-checked against institution records; they never override them silently."""
    facts = []

    def add(name, value, doc, m, group=1):
        facts.append({"name": name, "value": value, "doc_id": doc["id"], "doc_kind": doc.get("kind"),
                      "span": [m.start(group), m.end(group)], "method": "regex/v1"})
    for doc in documents or []:
        text = doc.get("text") or ""
        if m := re.search(r"(?:PNR|Booking reference)[^A-Z0-9\n]{0,12}([A-Z0-9]{6})\b", text):
            add("booking_ref", m.group(1), doc, m)
        if m := re.search(r"Total paid\s*(?:INR|Rs\.?|₹)\s*([\d,]+\.\d{2})", text, re.I):
            add("total_paid", fmt(D(m.group(1).replace(",", ""))), doc, m)
        if m := re.search(r"\b[Ff]light:?\s+([A-Z0-9]{2}-\d{3,4})\b", text):
            add("flight_no", m.group(1), doc, m)
        if doc.get("kind") == "cancellation_notice" and (m := re.search(r"Sent\s+(\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}) IST", text)):
            local = datetime.strptime(m.group(1), "%d-%b-%Y %H:%M").replace(tzinfo=IST)
            add("notified_at", local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), doc, m)
    return facts


# --------------------------------------------------------------------------- index

class ConsumerEvidenceIndex:
    def __init__(self, case: dict, rulebook: dict):
        self.case, self.rulebook = case, rulebook
        self.records, self.system_of = {}, {}
        for system, blk in case["sources"].items():
            for r in blk["records"]:
                self.records[r["id"]] = r
                self.system_of[r["id"]] = system
        d = case["dispute"]
        self.records[d["id"]], self.system_of[d["id"]] = d, "claim"
        self.documents = {doc["id"]: doc for doc in case.get("documents", [])}
        self.doc_facts = extract_doc_facts(case.get("documents", []))
        q_by_system = {q["system"]: q for q in case.get("queries", [])}
        as_of = ts(case["as_of"])
        self.lineage = {}
        for rid, r in self.records.items():
            system = self.system_of[rid]
            feed = case.get("feeds", {}).get(system, {})
            q = q_by_system.get(system, {})
            age = round((as_of - ts(feed["as_of"])).total_seconds() / 3600, 1) if feed.get("as_of") else None
            self.lineage[rid] = {"record_id": rid, "system": system, "type": r.get("type"),
                                 "source_kind": case.get("provenance", {}).get(system, "reclaim-intake" if system == "claim" else "unknown"),
                                 "query_id": q.get("query_id"), "selector": q.get("selector"), "retrieved_at": q.get("retrieved_at"),
                                 "content_hash": compute_evidence_hash(r), "feed_as_of": feed.get("as_of"), "age_hours": age,
                                 "fresh": system == "claim" or not self.is_stale(system), "rechecked": False, "recheck_match": None}
        for did, doc in self.documents.items():
            self.lineage[did] = {"record_id": did, "system": "documents", "type": doc.get("kind"),
                                 "source_kind": doc.get("provenance", "claimant-upload (fixture)"),
                                 "query_id": doc.get("reclaim_document_id"), "selector": "case documents",
                                 "retrieved_at": doc.get("retrieved_at"), "content_hash": compute_evidence_hash(doc.get("text", "")),
                                 "feed_as_of": None, "age_hours": None, "fresh": True, "rechecked": False, "recheck_match": None}

    def exists(self, rid) -> bool:
        return rid in self.records or rid in self.documents

    def get(self, rid):
        return self.records.get(rid)

    def of_type(self, rtype):
        return sorted((r for r in self.records.values() if r.get("type") == rtype), key=lambda r: r["id"])

    def is_stale(self, system: str) -> bool:
        feed = self.case.get("feeds", {}).get(system, {})
        limit = self.rulebook["freshness_max_age_hours"].get(system)
        if not feed.get("as_of") or limit is None or feed.get("live"):
            return False
        return (ts(self.case["as_of"]) - ts(feed["as_of"])).total_seconds() / 3600 > limit

    def doc_fact(self, name):
        hits = [f for f in self.doc_facts if f["name"] == name]
        return next((f for f in hits if f["doc_kind"] == "cancellation_notice"), hits[0] if hits else None)


# --------------------------------------------------------------------------- agent output (claims to verify)

def normalize_agent_run(run: dict | None, rulebook: dict, domain: str | None) -> dict:
    if not run:
        return {"available": False, "citations": [], "amount_claims": [], "texts": {}, "agent_trace": []}
    texts = {k: str(run.get(k) or "") for k in ("evidence_summary", "research_summary", "strategy", "appeal_draft", "final_answer")}
    amounts = []
    for field, text in texts.items():
        for m in INR_RE.finditer(text):
            amounts.append({"field": field, "amount": fmt(D(m.group(1).replace(",", ""))),
                            "context": text[max(0, m.start() - 60): m.end() + 40]})
    return {"available": True, "provenance": run.get("provenance", "reclaim-live"), "status": run.get("status"),
            "citations": [verify_citation(c, rulebook, domain) for c in run.get("citations", []) or []],
            "amount_claims": amounts, "texts": texts, "agent_trace": run.get("agent_trace") or [],
            "review_notes": run.get("review_notes") or [], "llm_call_count": run.get("llm_call_count"),
            "workflow_engine": run.get("workflow_engine"), "run_at": run.get("run_at"), "route": run.get("route")}


# --------------------------------------------------------------------------- contradictions

def contradictions(index: ConsumerEvidenceIndex, calc: dict, materiality: dict) -> list[dict]:
    """Cross-source disagreements on the same fact, labelled by kind. Engine conflicts carry their
    materiality (does choosing the other option change the amount owed?); document-vs-record checks
    are reported even when immaterial so a reviewer can see them."""
    out = []
    for c in calc["conflicts"]:
        out.append({"id": f"CX-{c['code']}", "kind": CONFLICT_KIND.get(c["code"], "OTHER"), "code": c["code"], "detail": c["detail"],
                    "records": c["cites"], "material": materiality.get(c["key"], True), "origin": "policy-engine"})
    bk = index.get(calc.get("booking_id")) if calc.get("booking_id") else None
    pay = index.get(calc.get("payment_id")) if calc.get("payment_id") else None
    ev = index.get(calc.get("event_id")) if calc.get("event_id") else None
    for f in index.doc_facts:
        if f["name"] == "total_paid" and bk and D(f["value"]) != D(bk["total_paid"]):
            out.append({"id": f"CX-DOC-FARE-{f['doc_id']}", "kind": "AMOUNT", "code": "DOCUMENT_FARE_MISMATCH",
                        "detail": f"{f['doc_id']} states total paid {f['value']}; {bk['id']} records {bk['total_paid']}",
                        "records": [f["doc_id"], bk["id"]], "material": False, "origin": "document-check"})
        if f["name"] == "total_paid" and pay and D(f["value"]) != D(pay["amount"]):
            out.append({"id": f"CX-DOC-PAY-{f['doc_id']}", "kind": "AMOUNT", "code": "DOCUMENT_PAYMENT_MISMATCH",
                        "detail": f"{f['doc_id']} states total paid {f['value']}; card capture {pay['id']} is {pay['amount']}",
                        "records": [f["doc_id"], pay["id"]], "material": False, "origin": "document-check"})
        if f["name"] == "booking_ref" and f["value"] != index.case["dispute"].get("booking_ref"):
            out.append({"id": f"CX-DOC-REF-{f['doc_id']}", "kind": "REFERENCE", "code": "DOCUMENT_REF_MISMATCH",
                        "detail": f"{f['doc_id']} names booking {f['value']}; the claim names {index.case['dispute'].get('booking_ref')}",
                        "records": [f["doc_id"], index.case["dispute"]["id"]], "material": True, "origin": "document-check"})
        if f["name"] == "notified_at" and ev and ev.get("notified_at") and not any(x["code"] == "NOTICE_TIME_CONFLICT" for x in out):
            gap = abs((ts(f["value"]) - ts(ev["notified_at"])).total_seconds()) / 3600
            if gap > 1:
                out.append({"id": f"CX-DOC-TIME-{f['doc_id']}", "kind": "TIME", "code": "DOCUMENT_NOTICE_DRIFT",
                            "detail": f"{f['doc_id']} and {ev['id']} disagree on notification time by {gap:.1f}h "
                                      "(same notice band, so the amount owed is unchanged)",
                            "records": [f["doc_id"], ev["id"]], "material": False, "origin": "document-check"})
    return out


# --------------------------------------------------------------------------- Meterless World Model

C_REL = [("card_payment", "booking_id", "pays-for"), ("card_credit", "payment_id", "credits"),
         ("airline_refund", "booking_id", "refund-claimed-for"), ("passenger_consent", "booking_id", "consent-for"),
         ("flight_event", "booking_id", "affects"), ("alternate_offer", "booking_id", "offered-for")]


def _iso(d):
    return d if "T" in str(d) else f"{d}T00:00:00.000Z"


def ingest_consumer_case(world: wm.WorldModel, case: dict, run_id: str | None = None) -> dict:
    """Every federated record and claimant document becomes a provenance-stamped observation keyed by its
    source id; typed edges are written with validFrom = the record's effective time (bitemporal)."""
    obs, ids = [], {}
    for system, blk in case["sources"].items():
        for rec in blk["records"]:
            ids[rec["id"]] = wm.external_id(rec.get("type", "record"), system, rec["id"])
            obs.append({"externalId": rec["id"], "type": rec.get("type", "record"), "system": system, "title": rec["id"],
                        "at": _iso(rec.get("recorded_at") or rec.get("effective_at") or case["as_of"]),
                        "attrs": {k: v for k, v in rec.items() if k not in ("id", "type")},
                        "source": {"kind": system, "by": "consumer-source-adapter", "runId": run_id}})
    for doc in case.get("documents", []):
        ids[doc["id"]] = wm.external_id("document", "documents", doc["id"])
        obs.append({"externalId": doc["id"], "type": "document", "system": "documents", "title": doc.get("title", doc["id"]),
                    "at": _iso(case["dispute"]["recorded_at"]), "text": doc.get("text", ""),
                    "attrs": {"kind": doc.get("kind"), "sha": compute_evidence_hash(doc.get("text", ""))},
                    "source": {"kind": doc.get("provenance", "claimant-upload"), "runId": run_id}})
    d = case["dispute"]
    ids[d["id"]] = wm.external_id("consumer_claim", "claims", d["id"])
    obs.append({"externalId": d["id"], "type": "consumer_claim", "system": "claims", "title": d["id"], "at": _iso(d["recorded_at"]),
                "attrs": {k: v for k, v in d.items() if k != "id"}, "source": {"kind": "reclaim-intake", "runId": run_id}})
    report = world.ingest(sorted(obs, key=lambda o: o["externalId"]))
    for system, blk in case["sources"].items():
        for rec in blk["records"]:
            for rtype, field, rel in C_REL:
                tgt = rec.get(field)
                if rec.get("type") == rtype and tgt in ids and tgt != rec["id"]:
                    world.relate(ids[rec["id"]], rel, ids[tgt], valid_from=_iso(rec.get("effective_at") or rec["recorded_at"]),
                                 source={"kind": system, "at": _iso(rec.get("recorded_at") or rec["effective_at"]),
                                         "by": "consumer-source-adapter", "runId": run_id})
    for b in (r for r in case["sources"]["airline_pss"]["records"] if r.get("type") == "booking"):
        if b.get("booking_ref") == d.get("booking_ref"):
            world.relate(ids[d["id"]], "disputes", ids[b["id"]], valid_from=_iso(d["recorded_at"]),
                         source={"kind": "reclaim-intake", "at": _iso(d["recorded_at"]), "runId": run_id})
    return {**report, "entities": len(world.entities), "relationships": len(world.relationships),
            "state_hash": wm.sha256_hex(world.state_shape_canonical())[:16], "ids": ids}


def consumer_fingerprint(case: dict) -> str:
    """What the decision depends on: records, claim, documents and feed health. A live feed's as_of is
    wall-clock query time, so it is excluded (otherwise every reload would look like a source change)."""
    feeds = {s: {"status": f.get("status"), **({} if f.get("live") else {"as_of": f.get("as_of")})}
             for s, f in case.get("feeds", {}).items()}
    return compute_evidence_hash({"sources": {s: b["records"] for s, b in case["sources"].items()}, "dispute": case["dispute"],
                                  "documents": [(d["id"], compute_evidence_hash(d.get("text", ""))) for d in case.get("documents", [])],
                                  "feeds": feeds})
