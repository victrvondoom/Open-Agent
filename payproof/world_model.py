"""Meterless World Model engine — Python implementation for PayProof.

Meterless engines are reference architectures that you implement in your own stack
(github.com/Meterless/Meterless, engines/world-model, Apache-2.0). This module follows
that spec and its TypeScript reference (`reference/src`):

  * stable content-derived ids (normalize_name: NFKD, strip marks/zero-width, lowercase, collapse spaces)
  * merge banding: >= 0.85 auto-merge, [0.82, 0.85) review, < 0.82 new
  * event-sourced canonical store; state is a fold over an append-only log
  * no provenance (kind + at), no write
  * bitemporal relationships: a new open edge with the same (from, type, context) and a
    different target closes the previous one; point-in-time queries respect validity
  * idempotent ingest: re-ingesting the same observations reports changed=False and leaves
    the canonical state shape byte-identical
  * every mutation appends an ordered audit entry

Not implemented (not needed by PayProof): stories/velocity scoring, enrichment queues,
custom views, facts conflict policies other than most-recent-wins.

How PayProof uses it (see `ingest_case`, `context_for`):
  1. Evidence intake: every investigation ingests the case's source records as externally
     keyed entities with provenance, plus typed, bitemporal relationships.
  2. Stale-evidence gate: actions store the World Model state shape at proposal; approval
     and execution re-ingest current sources and refuse when ingest reports changed=True.
  3. Context builder: the bounded model prompt is built from the World Model neighborhood
     of the disputed opportunity, not from ad-hoc record dumps.
  4. Evidence for judges: the audit is written as JSONL under logs/.
"""

import copy
import hashlib
import json
import re
import unicodedata

ENGINE = "meterless-world-model/py-0.1 (PayProof port of the Meterless reference)"


# ----------------------------------------------------------------------------- ids

def canonical_json(value) -> str:
    """Sorted keys, None members dropped (the reference drops `undefined`)."""
    if isinstance(value, dict):
        keys = sorted(k for k, v in value.items() if v is not None)
        return "{" + ",".join(json.dumps(k) + ":" + canonical_json(value[k]) for k in keys) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    return json.dumps(value)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


_MARKS = re.compile(r"[̀-ͯ]")
_ZERO_WIDTH = re.compile(r"[​-‍﻿]")


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = _ZERO_WIDTH.sub("", _MARKS.sub("", s)).lower()
    return re.sub(r"\s+", " ", s).strip()


def external_id(type_: str, system: str, id_: str) -> str:
    return f"{type_}:{system}:{id_}"


def entity_id_from_name(type_: str, name: str) -> str:
    return "ent_" + sha256_hex(f"{type_}:{normalize_name(name)}")[:16]


def relationship_id(frm, type_, to, context=None, valid_from=None) -> str:
    return "rel_" + sha256_hex(f"{frm}|{type_}|{to}|{context or ''}|{valid_from or ''}")[:16]


def fact_id(about, predicate, value, asserted_at, source_kind, source_url=None) -> str:
    return "fact_" + sha256_hex(f"{about}|{predicate}|{canonical_json(value)}|{asserted_at}|{source_kind}|{source_url or ''}")[:16]


# ----------------------------------------------------------------------------- resolution

def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = curr
    return prev[-1]


def name_similarity(a: str, b: str) -> float:
    a, b = normalize_name(a), normalize_name(b)
    m = max(len(a), len(b))
    return 1.0 if m == 0 else 1 - levenshtein(a, b) / m


def decide(similarity: float, auto_merge_at: float = 0.85, review_lower: float = 0.82) -> str:
    if similarity >= auto_merge_at:
        return "auto-merge"
    if similarity >= review_lower:
        return "review"
    return "new"


class ProvenanceError(ValueError):
    pass


# ----------------------------------------------------------------------------- store

class WorldModel:
    def __init__(self, namespace: str, clock=None):
        if not namespace:
            raise ValueError("WorldModel: namespace is required")
        self.namespace = namespace
        self.clock = clock
        self.events: list[dict] = []
        self.audit_log: list[dict] = []
        self.entities: dict[str, dict] = {}
        self.contexts: dict[str, dict] = {}
        self.relationships: dict[str, dict] = {}
        self.facts: dict[str, dict] = {}
        self.aliases: dict[str, str] = {}
        self.observations: dict[str, dict] = {}
        self.merge_queue: list[dict] = []

    # -- internals
    @staticmethod
    def _prov(source):
        if not source or not source.get("kind") or source.get("at") is None:
            raise ProvenanceError("World Model: every write carries provenance (kind + at). No provenance, no write.")
        return dict(source)

    def _append(self, kind, payload, at):
        ev = {"id": f"evt_{len(self.events) + 1}", "seq": len(self.events) + 1, "kind": kind,
              "payload": copy.deepcopy(payload), "schemaVersion": 1, "at": at}
        self.events.append(ev)
        self._fold(ev)
        return ev

    def _log(self, kind, actor, summary, event_id=None, run_id=None, at=None):
        self.audit_log.append({"seq": len(self.audit_log) + 1, "at": at or "1970-01-01T00:00:00.000Z", "kind": kind,
                               "actor": actor, "summary": summary, "eventId": event_id, "runId": run_id})

    def _fold(self, ev):
        p = ev["payload"]
        if ev["kind"] == "upsertEntity":
            cur = self.entities.get(p["id"])
            if cur:
                cur["attrs"] = {**cur["attrs"], **p["attrs"]}
                cur["updatedAt"], cur["source"] = p["updatedAt"], p["source"]
                if p.get("name"):
                    if p["name"] not in cur["aliases"]:
                        cur["aliases"].append(p["name"])
                    cur["name"] = p["name"]
            else:
                self.entities[p["id"]] = copy.deepcopy(p)
        elif ev["kind"] == "upsertContext":
            cur = self.contexts.get(p["id"])
            if cur:
                cur["attrs"] = {**cur["attrs"], **p["attrs"]}
                cur["updatedAt"] = p["updatedAt"]
            else:
                self.contexts[p["id"]] = copy.deepcopy(p)
        elif ev["kind"] == "relate":
            for other in self.relationships.values():
                if (other["from"] == p["from"] and other["type"] == p["type"]
                        and (other.get("context") or "") == (p.get("context") or "")
                        and other["to"] != p["to"] and not other.get("validTo") and not other.get("supersededBy")):
                    other["validTo"] = p.get("validFrom") or p["createdAt"]
                    other["supersededBy"] = p["id"]
            self.relationships.setdefault(p["id"], copy.deepcopy(p))
        elif ev["kind"] == "assertFact":
            self.facts.setdefault(p["id"], copy.deepcopy(p))
        elif ev["kind"] == "alias":
            self.aliases[p["aliasId"]] = p["primaryId"]

    def resolve_alias(self, id_):
        seen = set()
        while id_ in self.aliases and id_ not in seen:
            seen.add(id_)
            id_ = self.aliases[id_]
        return id_

    # -- writes
    def upsert_entity(self, type, source, name=None, external_key=None, attrs=None, state="active"):
        src = self._prov(source)
        name = name or (attrs or {}).get("name")
        if external_key:
            id_ = external_id(type, external_key["system"], external_key["id"])
        else:
            if not name:
                raise ValueError("World Model: a name-keyed entity needs a name")
            id_ = entity_id_from_name(type, name)
            for other in list(self.entities.values()):
                if other["type"] != type or other["id"] == id_ or not other.get("name"):
                    continue
                sim = name_similarity(name, other["name"])
                d = decide(sim)
                if d == "auto-merge":
                    self._append("alias", {"aliasId": id_, "primaryId": other["id"], "mergedAt": src["at"],
                                           "mergedBy": "resolver", "reason": f"similarity {sim:.3f}"}, src["at"])
                    self._log("auto-merge", "resolver", f"{name} -> {other['name']} ({sim:.3f})", at=src["at"])
                    return self._fold_entity(other["id"], type, attrs, src, name, state)
                if d == "review" and not any({q["leftId"], q["rightId"]} == {id_, other["id"]} for q in self.merge_queue):
                    self.merge_queue.append({"id": f"merge_{len(self.merge_queue) + 1}", "leftId": id_, "rightId": other["id"],
                                             "similarity": sim, "status": "pending", "proposedAt": src["at"]})
                    self._log("merge-proposed", "resolver", f"{name} ~ {other['name']} ({sim:.3f}) queued", at=src["at"])
        return self._fold_entity(id_, type, attrs, src, name, state)

    def _fold_entity(self, id_, type_, attrs, src, name, state="active"):
        rid = self.resolve_alias(id_)
        ent = {"type": type_, "id": rid, "attrs": dict(attrs or {}), "schemaVersion": 1, "source": src,
               "createdAt": src["at"], "updatedAt": src["at"], "name": name, "aliases": [name] if name else [],
               "state": state}
        ev = self._append("upsertEntity", ent, src["at"])
        self._log("upsertEntity", src.get("by", "system"), f"{rid} ({type_})", ev["id"], src.get("runId"), src["at"])
        return self.entities[rid]

    def upsert_context(self, type, source, external_key=None, attrs=None, parent=None):
        src = self._prov(source)
        if external_key:
            id_ = external_id(type, external_key["system"], external_key["id"])
        else:
            id_ = "ctx_" + sha256_hex(f"{type}:{canonical_json(attrs or {})}:{parent or ''}")[:16]
        ctx = {"type": type, "id": id_, "attrs": dict(attrs or {}), "parent": parent, "schemaVersion": 1,
               "source": src, "createdAt": src["at"], "updatedAt": src["at"]}
        ev = self._append("upsertContext", ctx, src["at"])
        self._log("upsertContext", src.get("by", "system"), f"{id_} ({type})", ev["id"], src.get("runId"), src["at"])
        return self.contexts[id_]

    def relate(self, frm, type, to, source, context=None, attrs=None, valid_from=None, valid_to=None):
        src = self._prov(source)
        frm, to = self.resolve_alias(frm), self.resolve_alias(to)
        id_ = relationship_id(frm, type, to, context, valid_from)
        if id_ in self.relationships:
            return self.relationships[id_]  # content-addressed no-op
        rel = {"id": id_, "from": frm, "type": type, "to": to, "context": context, "attrs": attrs,
               "validFrom": valid_from or src["at"], "validTo": valid_to, "schemaVersion": 1, "source": src,
               "createdAt": src["at"]}
        ev = self._append("relate", rel, src["at"])
        self._log("relate", src.get("by", "system"), f"{frm} -[{type}]-> {to}", ev["id"], src.get("runId"), src["at"])
        return self.relationships[id_]

    def assert_fact(self, about, predicate, value, source, confidence=0.5, context=None):
        """most-recent-wins conflict policy (the reference default)."""
        src = self._prov(source)
        about = self.resolve_alias(about)
        id_ = fact_id(about, predicate, value, src["at"], src["kind"], src.get("url"))
        if id_ in self.facts:
            return self.facts[id_]
        fact = {"id": id_, "about": about, "predicate": predicate, "value": value, "confidence": confidence,
                "context": context, "source": src, "assertedAt": src["at"]}
        rivals = [f for f in self.facts.values() if f["about"] == about and f["predicate"] == predicate and not f.get("supersededBy")]
        winner = fact
        for r in rivals:
            if r["assertedAt"] > winner["assertedAt"]:
                winner = r
        ev = self._append("assertFact", fact, src["at"])
        for f in [fact] + rivals:
            if f["id"] != winner["id"]:
                self.facts[f["id"]]["supersededBy"] = winner["id"]
        if about not in self.entities:
            self._append("upsertEntity", {"type": about.split(":")[0] if ":" in about else "entity", "id": about, "attrs": {},
                                          "schemaVersion": 1, "source": src, "createdAt": src["at"], "updatedAt": src["at"],
                                          "name": None, "aliases": [], "state": "emerging"}, src["at"])
        self.entities[about]["attrs"][predicate] = winner["value"]
        self._log("assertFact", src.get("by", "system"), f"{about}.{predicate} = {json.dumps(winner['value'])} (most-recent-wins)",
                  ev["id"], src.get("runId"), src["at"])
        return self.facts[id_]

    # -- ingest (canonical pipeline, observation-keyed checksums => idempotent)
    def ingest(self, observations: list[dict]) -> dict:
        run_id = "run_" + sha256_hex(canonical_json([o["externalId"] for o in observations]))[:12]
        before = self.state_shape_canonical()
        events_before = len(self.events)
        processed = skipped = 0
        for obs in observations:
            checksum = sha256_hex(canonical_json({"externalId": obs["externalId"], "title": obs.get("title"),
                                                  "text": obs.get("text") or "", "at": obs["at"],
                                                  "attrs": obs.get("attrs")}))
            prior = self.observations.get(obs["externalId"])
            if prior and prior["checksum"] == checksum:
                skipped += 1
                continue
            processed += 1
            src = self._prov({**obs["source"], "at": obs["at"]})
            type_ = obs.get("type", "item")
            ent = self._fold_entity(external_id(type_, obs.get("system", "ingest"), obs["externalId"]), type_,
                                    {"title": obs.get("title"), "text": obs.get("text"), **(obs.get("attrs") or {})}, src, obs.get("title"))
            mention_ids = []
            for m in obs.get("entities", []):
                mid = entity_id_from_name(m["type"], m["name"])
                self._fold_entity(mid, m["type"], None, src, m["name"])
                mid = self.resolve_alias(mid)
                mention_ids.append(mid)
                rid = relationship_id(ent["id"], "mentions", mid)
                if rid not in self.relationships:
                    self._append("relate", {"id": rid, "from": ent["id"], "type": "mentions", "to": mid, "validFrom": src["at"],
                                            "schemaVersion": 1, "source": src, "createdAt": src["at"]}, src["at"])
            self.observations[obs["externalId"]] = {"id": "obs_" + sha256_hex(obs["externalId"])[:12], "externalId": obs["externalId"],
                                                    "entityId": ent["id"], "checksum": checksum, "at": obs["at"],
                                                    "entityIds": sorted(mention_ids)}
        after = self.state_shape_canonical()
        report = {"runId": run_id, "processed": processed, "skippedUnchanged": skipped,
                  "eventsAppended": len(self.events) - events_before, "changed": before != after}
        self._log("ingest", "pipeline", f"run {run_id}: {processed} processed, {skipped} skipped", None, run_id,
                  observations[0]["at"] if observations else None)
        return report

    # -- reads
    def state_shape(self):
        by_id = lambda d: [d[k] for k in sorted(d)]
        return {"entities": by_id(self.entities), "contexts": by_id(self.contexts), "relationships": by_id(self.relationships),
                "facts": by_id(self.facts), "observations": [self.observations[k] for k in sorted(self.observations)]}

    def state_shape_canonical(self) -> str:
        return canonical_json(self.state_shape())

    def neighbors_of(self, id_, via=None, in_context=None, at=None):
        rid = self.resolve_alias(id_)
        out = []
        for rel in self.relationships.values():
            if via and rel["type"] != via:
                continue
            if in_context and rel.get("context") != in_context:
                continue
            if at is not None:
                if rel.get("validFrom") and at < rel["validFrom"]:
                    continue
                if rel.get("validTo") and at >= rel["validTo"]:
                    continue
            elif rel.get("validTo"):
                continue  # closed edges excluded from "now" queries
            other = rel["to"] if rel["from"] == rid else rel["from"] if rel["to"] == rid else None
            if other and other in self.entities:
                out.append(self.entities[other])
        return sorted(out, key=lambda e: e["id"])

    def audit(self):
        return list(self.audit_log)


# ----------------------------------------------------------------------------- PayProof wiring

REL_TYPES = [  # (record type, field, relationship type) — mirrors evidence.REL
    ("split", "crm_user_id", "credits"), ("split", "opportunity_id", "split-of"),
    ("opportunity", "owner", "owned-by"), ("contract", "opportunity_id", "contract-for"),
    ("amendment", "contract_id", "amends"), ("invoice", "contract_id", "bills"),
    ("payment", "invoice_id", "pays"), ("credit_note", "invoice_id", "credits-invoice"),
    ("refund", "invoice_id", "refunds"), ("payroll_line", "batch_id", "in-batch"),
    ("payroll_line", "employee_id", "paid-to"), ("payroll_line", "reference_id", "references"),
    ("policy_exception", "opportunity_id", "modifies"),
]


def _iso(d):
    return d if "T" in d else d + "T00:00:00.000Z"


def ingest_case(world: WorldModel, case: dict, run_id: str | None = None) -> dict:
    """Ingest a case's source snapshot. Each record is one observation keyed by its source
    record id, with provenance = (source system, recorded_at). Typed relationships are then
    written with validFrom = the record's *effective* time (bitemporal: effective vs recorded)."""
    obs, ids = [], {}
    for system, block in case["sources"].items():
        for rec in block["records"]:
            type_ = rec.get("type", "record")
            ids[rec["id"]] = external_id(type_, system, rec["id"])
            obs.append({"externalId": rec["id"], "type": type_, "system": system, "title": rec["id"],
                        "at": _iso(rec.get("recorded_at") or rec.get("effective_at") or "1970-01-01"),
                        "attrs": {k: v for k, v in rec.items() if k not in ("id", "type")},
                        "source": {"kind": block["system"], "by": "payproof-source-adapter", "runId": run_id}})
    d = case["dispute"]
    ids[d["id"]] = external_id("dispute", "disputes", d["id"])
    obs.append({"externalId": d["id"], "type": "dispute", "system": "disputes", "title": d["id"], "at": _iso(d["recorded_at"]),
                "attrs": {k: v for k, v in d.items() if k != "id"}, "source": {"kind": "dispute-intake", "runId": run_id}})
    report = world.ingest(sorted(obs, key=lambda o: o["externalId"]))
    for system, block in case["sources"].items():
        for rec in block["records"]:
            for rtype, field, rel in REL_TYPES:
                tgt = rec.get(field)
                if rec.get("type") == rtype and tgt in ids and tgt != rec["id"]:
                    world.relate(ids[rec["id"]], rel, ids[tgt], valid_from=_iso(rec.get("effective_at") or rec["recorded_at"]),
                                 source={"kind": block["system"], "at": _iso(rec.get("recorded_at") or rec["effective_at"]),
                                         "by": "payproof-source-adapter", "runId": run_id})
    for tgt, rel in ((d["employee_id"], "filed-by"), (d["opportunity_id"], "disputes")):
        if tgt in ids:
            world.relate(ids[d["id"]], rel, ids[tgt], valid_from=_iso(d["recorded_at"]),
                         source={"kind": "dispute-intake", "at": _iso(d["recorded_at"]), "runId": run_id})
    return {**report, "entities": len(world.entities), "relationships": len(world.relationships),
            "state_hash": sha256_hex(world.state_shape_canonical())[:16], "ids": ids}


def context_for(world: WorldModel, root: str, depth: int = 2, limit: int = 40) -> list[dict]:
    """Context builder: bounded breadth-first neighborhood of `root`, with provenance.
    Feeds the model prompt so it only sees grounded, provenance-stamped entities."""
    seen, frontier, out = {root}, [root], []
    for _ in range(depth):
        nxt = []
        for node in frontier:
            for ent in world.neighbors_of(node):
                if ent["id"] in seen:
                    continue
                seen.add(ent["id"])
                nxt.append(ent["id"])
                a = ent["attrs"]
                out.append({"id": ent["id"].split(":")[-1], "type": ent["type"], "source": ent["source"]["kind"],
                            "recorded_at": ent["source"]["at"],
                            **{k: a[k] for k in ("amount", "tcv", "new_tcv", "effective_at", "value_date", "issued_date",
                                                 "signed_date", "line_type", "stage") if a.get(k) is not None}})
        frontier = nxt
    return sorted(out, key=lambda e: e["id"])[:limit]


def write_audit_jsonl(world: WorldModel, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for entry in world.audit():
            fh.write(json.dumps({"engine": ENGINE, "namespace": world.namespace, **entry}) + "\n")
