"""Normalized evidence layer: record index with provenance, temporal identity
resolution and the evidence graph.

Original records are never modified. Every normalized fact keeps its source
system, source record id, effective time, ingestion time and transformation history.
"""

import re

from .money import D

MONEY_FIELDS = {"amount", "tcv", "new_tcv", "rate", "rate_override", "pct", "claimed_shortfall"}
DATE_FIELDS = {"effective_at", "close_date", "signed_date", "effective_date", "issued_date", "value_date",
               "posted_date", "measurement_cutoff"}


class EvidenceIndex:
    def __init__(self, case: dict):
        self.case = case
        self.records: dict[str, dict] = {}
        self.system_of: dict[str, str] = {}
        self.system_names = {}
        self.duplicate_ids: list[str] = []
        for system, block in case["sources"].items():
            self.system_names[system] = block["system"]
            for rec in block["records"]:
                if rec["id"] in self.records:
                    self.duplicate_ids.append(rec["id"])
                    continue
                self.records[rec["id"]] = rec
                self.system_of[rec["id"]] = system
        d = case["dispute"]
        self.records[d["id"]] = d
        self.system_of[d["id"]] = "disputes"
        self.system_names["disputes"] = "dispute-intake"

    def add_simulated(self, records: list[dict]):
        """Rows written by the simulated action adapter. Kept in their own system, never in source snapshots."""
        if records:
            self.system_names["sim_ledger"] = "payroll-sim ledger (simulated executions)"
        for rec in records:
            self.records[rec["id"]] = rec
            self.system_of[rec["id"]] = "sim_ledger"

    def exists(self, rid: str) -> bool:
        return rid in self.records

    def of_type(self, rtype: str):
        return [r for r in self.records.values() if r.get("type") == rtype]

    def get(self, rid):
        return self.records.get(rid)

    def provenance(self, rid: str) -> dict:
        rec = self.records[rid]
        system = self.system_of[rid]
        return {"record_id": rid, "source_system": system, "source_name": self.system_names[system],
                "source_type": rec.get("type", "dispute"), "effective_at": rec.get("effective_at"),
                "recorded_at": rec.get("recorded_at")}

    def normalized_facts(self):
        """Typed facts with transformation history (exact decimal parsing, date checks)."""
        facts = []
        for rid, rec in self.records.items():
            for field, value in rec.items():
                if field in ("id", "type") or value is None:
                    continue
                transforms = []
                norm = value
                if field in MONEY_FIELDS:
                    norm = str(D(value))
                    transforms.append("str->Decimal (exact)")
                elif field in DATE_FIELDS:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)[:10]):
                        transforms.append("INVALID_DATE")
                    norm = str(value)[:10]
                    transforms.append("ISO-8601 date")
                else:
                    continue
                facts.append({"fact_id": f"{rid}.{field}", "record_id": rid, "field": field, "value": norm,
                              "raw": value, **self.provenance(rid), "transforms": transforms})
        return facts


def _norm_name(n: str) -> str:
    return re.sub(r"[^a-z ]", "", n.lower()).strip()


def resolve_identity(employee: dict, crm_users: list[dict]) -> dict:
    """Match an HRIS employee to CRM users. Email (primary or HRIS-recorded alias) is a
    strong signal; names are weak. Exactly one strong match resolves. Weak-only matches
    are never merged silently."""
    emails = {employee["email"].lower()}
    aliases = {e.lower() for e in employee.get("alt_emails", [])}
    emp_name = _norm_name(employee["name"])
    first, last = (emp_name.split() + [""])[:2] if emp_name else ("", "")
    candidates = []
    for u in crm_users:
        signals, strong = [], False
        ue = u["email"].lower()
        if ue in emails:
            signals.append("email exact match (HRIS primary)")
            strong = True
        elif ue in aliases:
            signals.append("email matches HRIS-recorded alias")
            strong = True
        un = _norm_name(u["name"])
        if un == emp_name:
            signals.append("full name match")
        elif un.split() and un.split()[-1] == last and un[:1] == first[:1]:
            signals.append("initial + surname match")
        if signals:
            candidates.append({"crm_user_id": u["id"], "name": u["name"], "strength": "STRONG" if strong else "WEAK",
                               "signals": signals})
    strong = [c for c in candidates if c["strength"] == "STRONG"]
    if len(strong) == 1:
        status, chosen = "RESOLVED", strong[0]["crm_user_id"]
    elif len(strong) > 1:
        status, chosen = "AMBIGUOUS", None
    elif candidates:
        status, chosen = "AMBIGUOUS" if len(candidates) > 1 else "WEAK_ONLY", None
    else:
        status, chosen = "UNMATCHED", None
    return {"employee_id": employee["id"], "status": status, "crm_user_id": chosen, "candidates": candidates}


REL = [
    ("split", "crm_user_id", "CREDITS"), ("split", "opportunity_id", "SPLIT_OF"),
    ("opportunity", "owner", "OWNED_BY"), ("contract", "opportunity_id", "CONTRACT_FOR"),
    ("amendment", "contract_id", "AMENDS"), ("invoice", "contract_id", "BILLS"),
    ("payment", "invoice_id", "PAYS"), ("credit_note", "invoice_id", "CREDITS_INVOICE"),
    ("refund", "invoice_id", "REFUNDS"), ("payroll_line", "batch_id", "IN_BATCH"),
    ("payroll_line", "employee_id", "PAID_TO"), ("payroll_line", "reference_id", "REFERENCES"),
    ("policy_exception", "opportunity_id", "MODIFIES"),
]


def build_graph(index: EvidenceIndex, identity: dict, flags: dict[str, list[str]], used: set[str]):
    nodes, edges = [], []
    for rid, rec in index.records.items():
        rtype = rec.get("type", "dispute")
        label = rec.get("name") or rec.get("account") or rec.get("line_type") or rtype
        amt = rec.get("amount") or rec.get("tcv") or rec.get("new_tcv") or rec.get("claimed_shortfall")
        nodes.append({"id": rid, "type": rtype, "system": index.system_of[rid], "label": label,
                      "amount": amt, "effective_at": rec.get("effective_at"), "recorded_at": rec.get("recorded_at"),
                      "flags": flags.get(rid, []), "used_in_calculation": rid in used})
    for rid, rec in index.records.items():
        for rtype, field, rel in REL:
            if rec.get("type") == rtype and rec.get(field) and index.exists(rec[field]) and rec[field] != rid:
                edges.append({"from": rid, "to": rec[field], "rel": rel, "status": "observed"})
        if rec.get("type") == "invoice" and not rec.get("contract_id") and rec.get("opportunity_id"):
            edges.append({"from": rid, "to": rec["opportunity_id"], "rel": "BILLS", "status": "observed"})
    d = index.case["dispute"]
    edges.append({"from": d["id"], "to": d["employee_id"], "rel": "FILED_BY", "status": "observed"})
    edges.append({"from": d["id"], "to": d["opportunity_id"], "rel": "DISPUTES", "status": "observed"})
    for c in identity["candidates"]:
        resolved = c["crm_user_id"] == identity["crm_user_id"]
        edges.append({"from": identity["employee_id"], "to": c["crm_user_id"], "rel": "SAME_PERSON",
                      "status": "resolved" if resolved else "candidate", "signals": c["signals"]})
    return {"nodes": nodes, "edges": edges}
