"""Meterless H-MEM engine — Python port of the official reference implementation
(github.com/Meterless/Meterless, engines/hmem/reference/src, Apache-2.0).

Implemented to the reference's exact tier: records rejected without a source; feedback deltas
(+0.05 / -0.03 / -0.20, clamped, `review` tag); the hybrid retrieval formula

    raw   = 0.35*semantic + 0.20*keyword + 0.10*tag + 0.10*domain + 0.15*entity
          + 0.05*layer + 0.05*recency - 0.20*superseded
    score = clamp01(raw) * confidence            (threshold 0.35 on the final score, top 5)

an append-only trust ledger with previous/new state; conflict detection with the 0.70
auto-resolve gate (the loser is marked supersededBy and never deleted); a preview-first sleep
cycle with backup and guardrails; and dreaming, which never materializes before approval.
The embedder is the reference's deterministic FNV-1a 64-dim hash embedder.

How PayProof uses it (`PrecedentMemory` below): only *verified* outcomes (a human-approved
action whose postcondition passed) become precedents, tagged with the case's evidence patterns
and citing case id, receipt id and proof hash. Investigations retrieve precedents from other
cases only (never their own), and precedents never feed the money calculation: they are shown
to the reviewer and checked for consistency with the current recommendation.
"""

import copy
import json
import math
import re
from pathlib import Path

DAY_MS = 24 * 60 * 60 * 1000
FEEDBACK_DELTAS = {"helpful": 0.05, "not_helpful": -0.03, "wrong": -0.2}
DEFAULTS = {"retrievalTopN": 5, "retrievalThreshold": 0.35, "consolidationDays": 7, "archiveMinDays": 30,
            "archiveMaxAccess": 2, "synthesisCosine": 0.82, "dreamClusterMinSize": 2, "dreamRelatedness": 0.35,
            "maxDreamProposalsPerType": 8, "conflictAutoResolveGate": 0.7, "entityCap": 10, "relatedCap": 5,
            "recencyDays": 14}
LAYER_WEIGHT = {"long_term": 1.0, "working": 0.8, "short_term": 0.6}
HUB_THRESHOLD = 3
DIM = 64


def clamp01(x):
    return min(1.0, max(0.0, x))


# ----------------------------------------------------------------------------- embeddings

def tokenize(text):
    return [t for t in re.sub(r"[^a-z0-9\s]", " ", text.lower()).split() if len(t) > 1]


def _fnv1a(s):
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def embed(text):
    vec = [0.0] * DIM
    for token in tokenize(text):
        h = _fnv1a(token)
        sign = 1 if (h >> 8) % 2 == 0 else -1
        vec[h % DIM] += sign * (1 + ((h >> 16) % 8) / 8)
    norm = math.sqrt(sum(v * v for v in vec))
    return vec if norm == 0 else [v / norm for v in vec]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / (len(sa) + len(sb) - inter)


def snapshot(rec):
    out = copy.deepcopy(rec)
    out.pop("embedding", None)
    return out


# ----------------------------------------------------------------------------- services

class TrustLedger:
    """Append-only. Entries are never mutated or deleted."""

    def __init__(self, clock, persist_dir=None):
        self.clock, self.entries = clock, []
        self.file = Path(persist_dir) / "ledger.jsonl" if persist_dir else None
        if self.file and self.file.exists():
            self.entries = [json.loads(line) for line in self.file.read_text().splitlines() if line]

    def log(self, memory_id, action, actor, previous_state=None, new_state=None, details=None):
        entry = {"memoryId": memory_id, "action": action, "actor": actor, "timestamp": self.clock()}
        if previous_state is not None:
            entry["previousState"] = previous_state
        if new_state is not None:
            entry["newState"] = new_state
        if details is not None:
            entry["details"] = details
        self.entries.append(entry)
        if self.file:
            with self.file.open("a") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry

    def history(self, memory_id):
        return [e for e in self.entries if e["memoryId"] == memory_id]

    def stats(self):
        out = {}
        for e in self.entries:
            out[e["action"]] = out.get(e["action"], 0) + 1
        return out


TECH_TERMS = ["react", "python", "typescript", "javascript", "rust", "sqlite", "postgres", "indexeddb", "node", "docker",
              "graphql", "redis", "webrtc", "tauri", "electron", "llm", "embedding"]
DOMAIN_KEYWORDS = {
    "tech": ["code", "bug", "api", "database", "deploy", "framework", "library", "server"] + TECH_TERMS,
    "work": ["meeting", "deadline", "client", "project", "sprint", "review", "report"],
    "personal": ["family", "hobby", "prefer", "like", "dislike", "morning", "evening"],
}
CORRECTION = re.compile(r"\b(actually|instead|no longer|not anymore|changed to|correction)\b", re.I)


class MemoryStore:
    def __init__(self, clock, ledger, actor, persist_dir=None):
        self.clock, self.ledger, self.actor = clock, ledger, actor
        self.records, self.seq = {}, 0
        self.state_file = Path(persist_dir) / "state.json" if persist_dir else None
        if self.state_file:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            if self.state_file.exists():
                saved = json.loads(self.state_file.read_text())
                self.seq = saved["seq"]
                self.records = {r["id"]: r for r in saved["records"]}

    def persist(self):
        if self.state_file:
            recs = [self.records[k] for k in sorted(self.records)]
            self.state_file.write_text(json.dumps({"seq": self.seq, "records": recs}, indent=2) + "\n")

    def add(self, content, source, type="general", layer="working", tags=None, confidence=0.7, provenance=None,
            chat_id=None, mission_id=None, supersedes=None, derived_from=None):
        if not source or not str(source).strip():
            raise ValueError("H-MEM: a memory record with no source must be rejected by construction (AGENTS.md section 2)")
        now = self.clock()
        self.seq += 1
        tags = list(tags or [])
        domain = self.classify_domain(content, tags, type)
        rec = {"id": f"mem-{self.seq}", "content": content, "type": type, "layer": layer, "timestamp": now,
               "lastAccessed": now, "accessCount": 0, "tags": tags, "embedding": embed(content),
               "confidence": clamp01(confidence), "source": source,
               "provenance": provenance or {"origin": "manual", "learnedAt": now, "label": source},
               "chatId": chat_id, "missionId": mission_id, "domain": domain,
               "namespace": self._namespace(domain, type), "entities": self.extract_entities(content),
               "relatedTo": [], "supersedes": supersedes, "supersededBy": None, "derivedFrom": derived_from}
        self._discover_relationships(rec)
        self.records[rec["id"]] = rec
        self.ledger.log(rec["id"], "create", self.actor, new_state=snapshot(rec))
        self.persist()
        return rec

    def get(self, mid):
        return self.records.get(mid)

    def all(self):
        return list(self.records.values())

    def _must(self, mid):
        if mid not in self.records:
            raise KeyError(f"H-MEM: unknown memory id {mid}")
        return self.records[mid]

    def update(self, mid, **patch):
        rec = self._must(mid)
        prev = snapshot(rec)
        rec.update(patch)
        self.ledger.log(mid, "update", self.actor, previous_state=prev, new_state=snapshot(rec))
        self.persist()
        return rec

    def delete(self, mid, reason):
        rec = self.records.pop(mid)
        self.ledger.log(mid, "delete", self.actor, previous_state=snapshot(rec), details={"reason": reason})
        self.persist()

    def touch(self, mid):
        rec = self._must(mid)
        rec["lastAccessed"] = self.clock()
        rec["accessCount"] += 1

    def promote(self, mid, layer):
        rec = self._must(mid)
        prev = snapshot(rec)
        rec["layer"] = layer
        self.ledger.log(mid, "promote", self.actor, previous_state=prev, new_state=snapshot(rec))
        self.persist()

    def snapshot_all(self):
        return {"records": copy.deepcopy(list(self.records.values())), "seq": self.seq}

    def restore_all(self, records, seq):
        self.records = {r["id"]: copy.deepcopy(r) for r in records}
        self.seq = seq
        self.persist()

    def classify_domain(self, content, tags, type):
        for t in tags:
            if t.startswith("project:"):
                return t[len("project:"):]
            if t.startswith("tech:"):
                return "tech"
        tokens = set(tokenize(content))
        best, best_score = "general", 0
        for domain, kws in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in kws if kw in tokens)
            if domain == "personal" and type in ("personal", "preference"):
                score += 1
            if score > best_score:
                best, best_score = domain, score
        return best if best_score > 0 else "general"

    @staticmethod
    def _namespace(domain, type):
        bucket = "profile" if type in ("preference", "personal") else "facts" if type == "factual" else "notes"
        return f"{domain}/{bucket}"

    def extract_entities(self, content):
        ents = []
        for t in tokenize(content):
            if t in TECH_TERMS and t not in ents:
                ents.append(t)
        for m in re.finditer(r"\b([A-Z][a-zA-Z]{2,})\b", content):
            norm = m.group(1).lower()
            if norm not in ("the", "this", "that", "with") and norm not in ents:
                ents.append(norm)
        return ents[:DEFAULTS["entityCap"]]

    def _discover_relationships(self, rec):
        for other in self.records.values():
            if len(rec["relatedTo"]) >= DEFAULTS["relatedCap"]:
                break
            shared = [e for e in other["entities"] if e in rec["entities"]]
            sim = cosine(rec["embedding"], other["embedding"])
            if not rec["supersedes"] and sim > 0.85 and CORRECTION.search(rec["content"]):
                rec["supersedes"] = other["id"]
                continue
            if shared and other["domain"] == rec["domain"]:
                rec["relatedTo"].append(other["id"])
                if len(other["relatedTo"]) < DEFAULTS["relatedCap"] and rec["id"] not in other["relatedTo"]:
                    other["relatedTo"].append(rec["id"])


class Retrieval:
    def __init__(self, store, ledger, clock, actor):
        self.store, self.ledger, self.clock, self.actor = store, ledger, clock, actor

    def _score(self, m, q_emb, q_tokens, q_entities, q_domain):
        semantic = clamp01(cosine(q_emb, m["embedding"]))
        keyword = jaccard(q_tokens, tokenize(m["content"]))
        tag = jaccard(q_tokens, [t.lower() for t in m["tags"]])
        domain = 1 if m["domain"] == q_domain else 0
        entity = jaccard(q_entities, m["entities"])
        layer = LAYER_WEIGHT[m["layer"]]
        recency = math.exp(-((self.clock() - m["lastAccessed"]) / DAY_MS) / DEFAULTS["recencyDays"])
        superseded = 1 if m.get("supersededBy") else 0
        raw = (0.35 * semantic + 0.2 * keyword + 0.1 * tag + 0.1 * domain + 0.15 * entity
               + 0.05 * layer + 0.05 * recency - 0.2 * superseded)
        return clamp01(raw) * m["confidence"]

    def query(self, query, top_n=None, threshold=None, chat_id=None, where=None):
        q_emb, q_tokens = embed(query), tokenize(query)[:8]
        q_entities = self.store.extract_entities(query)
        q_domain = self.store.classify_domain(query, [], "general")
        threshold = DEFAULTS["retrievalThreshold"] if threshold is None else threshold
        top_n = DEFAULTS["retrievalTopN"] if top_n is None else top_n
        scored = []
        for m in self.store.all():
            if chat_id and m.get("chatId") and m["chatId"] != chat_id:
                continue
            if where and not where(m):
                continue
            s = self._score(m, q_emb, q_tokens, q_entities, q_domain)
            if s >= threshold:
                scored.append({"memory": m, "relevance": s})
        scored.sort(key=lambda x: (-x["relevance"], x["memory"]["id"]))
        top = scored[:top_n]
        for t in top:
            self.store.touch(t["memory"]["id"])
            self.ledger.log(t["memory"]["id"], "read", self.actor, details={"query": query})
        strategy = "minimal" if len(top) <= 1 else "personal" if any(t["memory"]["type"] in ("personal", "preference") for t in top) else "comprehensive"
        return {"memories": top, "context": self.format_reinjection(top),
                "trace": {"retrievalReason": f'hybrid ranking for "{query}" (domain: {q_domain})', "strategy": strategy,
                          "scores": {t["memory"]["id"]: round(t["relevance"], 4) for t in top}}}

    @staticmethod
    def format_reinjection(items):
        if not items:
            return ""
        by_domain = {}
        for it in items:
            by_domain.setdefault(it["memory"]["domain"], []).append(it)
        lines = ["[MEMORY CONTEXT]"]
        for domain in sorted(by_domain):
            lines.append(f"## {domain}")
            for it in by_domain[domain]:
                m = it["memory"]
                marker = {"long_term": "LT", "working": "WK"}.get(m["layer"], "ST")
                ents = f" (entities: {', '.join(m['entities'])})" if m["entities"] else ""
                lines.append(f"- [{marker}] {m['content']}{ents} <{m['id']}>")
        lines.append("[/MEMORY CONTEXT]")
        return "\n".join(lines)

    def feedback(self, mid, kind):
        m = self.store.get(mid)
        if not m:
            raise KeyError(f"H-MEM: unknown memory id {mid}")
        prev = snapshot(m)
        if kind == "helpful":
            m["accessCount"] += 1
        m["confidence"] = clamp01(m["confidence"] + FEEDBACK_DELTAS[kind])
        if kind == "wrong" and "review" not in m["tags"]:
            m["tags"].append("review")
        self.ledger.log(mid, "feedback", self.actor, previous_state=prev, new_state=snapshot(m),
                        details={"kind": kind, "delta": FEEDBACK_DELTAS[kind]})
        self.store.persist()


OPPOSING_PAIRS = [(re.compile(r"\balways\b", re.I), re.compile(r"\bnever\b", re.I)),
                  (re.compile(r"\benable[ds]?\b", re.I), re.compile(r"\bdisable[ds]?\b", re.I)),
                  (re.compile(r"\bprefer[s]?\b", re.I), re.compile(r"\bavoid[s]?|dislike[s]?\b", re.I)),
                  (re.compile(r"\bon\b", re.I), re.compile(r"\boff\b", re.I)),
                  (re.compile(r"\byes\b", re.I), re.compile(r"\bno\b", re.I))]


class Conflicts:
    def __init__(self, store, ledger, clock, actor):
        self.store, self.ledger, self.clock, self.actor = store, ledger, clock, actor
        self.found, self.seq = [], 0

    def scan(self):
        out, recs = [], self.store.all()
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                c = self._check(recs[i], recs[j])
                if c:
                    out.append(c)
                    self.found.append(c)
                    self.ledger.log(c["memoryA"], "conflict_detected", self.actor,
                                    details={"with": c["memoryB"], "reason": c["reason"], "confidence": c["confidence"]})
        return out

    def _check(self, a, b):
        if b["id"] in (a.get("supersedes"), a.get("supersededBy")) or a["id"] in (b.get("supersedes"), b.get("supersededBy")):
            return None
        sim = cosine(a["embedding"], b["embedding"])
        reason, conf = "", 0.0
        for p, q in OPPOSING_PAIRS:
            if (p.search(a["content"]) and q.search(b["content"])) or (q.search(a["content"]) and p.search(b["content"])):
                if sim > 0.5:
                    reason, conf = "opposing phrase pair on similar content", 0.5 + 0.3 * sim
        if not reason and sim > 0.8:
            na, nb = re.findall(r"\d+(?:\.\d+)?", a["content"]), re.findall(r"\d+(?:\.\d+)?", b["content"])
            if na and nb and na != nb:
                reason, conf = "high-similarity conflicting numeric values", 0.55 + 0.25 * sim
        if not reason:
            return None
        if any(e in b["entities"] for e in a["entities"]):
            conf += 0.1
        if a["domain"] == b["domain"]:
            conf += 0.05
        if b["id"] in a["relatedTo"]:
            conf -= 0.1
        self.seq += 1
        return {"id": f"conflict-{self.seq}", "memoryA": a["id"], "memoryB": b["id"], "reason": reason,
                "confidence": clamp01(conf), "resolved": False}

    def auto_resolve(self, conflict):
        a, b = self.store.get(conflict["memoryA"]), self.store.get(conflict["memoryB"])

        def score(m):
            return (0.3 * (m["lastAccessed"] / max(1, self.clock())) + 0.2 * min(1, m["accessCount"] / 10)
                    + 0.25 * m["confidence"] + 0.1 * min(1, len(m["content"]) / 200)
                    + 0.15 * (1 if m["provenance"]["origin"] == "user_correction" else 0.5))
        sa, sb = score(a), score(b)
        margin = abs(sa - sb) / max(sa, sb)
        decision = clamp01(conflict["confidence"] * 0.6 + margin * 0.8)
        if decision < DEFAULTS["conflictAutoResolveGate"]:
            return "queued"
        winner, loser = (a, b) if sa >= sb else (b, a)
        prev = snapshot(loser)
        loser["supersededBy"] = winner["id"]  # kept and penalized, never deleted
        conflict["resolved"] = True
        conflict["resolution"] = "keep_a" if winner["id"] == conflict["memoryA"] else "keep_b"
        self.ledger.log(loser["id"], "conflict_resolved", self.actor, previous_state=prev, new_state=snapshot(loser),
                        details={"conflictId": conflict["id"], "winner": winner["id"], "decisionConfidence": round(decision, 3)})
        self.store.persist()
        return "resolved"

    def queue(self):
        return [c for c in self.found if not c["resolved"]]


class Sleep:
    def __init__(self, store, ledger, clock, actor):
        self.store, self.ledger, self.clock, self.actor = store, ledger, clock, actor
        self.backups, self.backup_seq = {}, 0

    def preview(self):
        now, recs = self.clock(), self.store.all()
        referenced = set()
        for m in recs:
            referenced.update(m["relatedTo"])
            if m.get("supersedes"):
                referenced.add(m["supersedes"])
            referenced.update(m.get("derivedFrom") or [])
        consolidate = [m["id"] for m in recs if m["layer"] == "short_term" and now - m["lastAccessed"] >= DEFAULTS["consolidationDays"] * DAY_MS]
        archive = []
        for m in recs:
            if not (now - m["timestamp"] >= DEFAULTS["archiveMinDays"] * DAY_MS and m["accessCount"] <= DEFAULTS["archiveMaxAccess"]
                    and m["id"] not in referenced):
                continue
            if m.get("supersedes") or (m.get("derivedFrom") or []) or len(m["relatedTo"]) >= HUB_THRESHOLD:
                continue  # guardrails: superseding, derived, hubs are never archived
            archive.append(m["id"])
        synth, used = [], set()
        for i, a in enumerate(recs):
            if a["id"] in used:
                continue
            group = [a] + [b for b in recs[i + 1:] if b["id"] not in used and cosine(a["embedding"], b["embedding"]) >= DEFAULTS["synthesisCosine"]]
            if len(group) >= 2:
                used.update(g["id"] for g in group)
                synth.append([g["id"] for g in group])
        return {"toConsolidate": consolidate, "toArchive": archive, "toSynthesize": synth}

    def execute(self, plan=None):
        plan = plan or self.preview()
        self.backup_seq += 1
        backup_id = f"backup-{self.backup_seq}"
        self.backups[backup_id] = self.store.snapshot_all()
        log = [f"backup {backup_id} created"]
        for mid in plan["toConsolidate"]:
            if self.store.get(mid):
                self.store.promote(mid, "long_term")
                self.ledger.log(mid, "sleep_consolidate", self.actor, details={"from": "short_term", "to": "long_term"})
                log.append(f"consolidated {mid}")
        for mid in plan["toArchive"]:
            m = self.store.get(mid)
            if m:
                self.ledger.log(mid, "sleep_archive", self.actor, details={"age": self.clock() - m["timestamp"], "accessCount": m["accessCount"]})
                self.store.delete(mid, "sleep archive")
                log.append(f"archived {mid}")
        synthesized = 0
        for group in plan["toSynthesize"]:
            members = [self.store.get(g) for g in group if self.store.get(g)]
            if len(members) < 2:
                continue
            merged = self.store.add(content="Synthesis: " + " | ".join(m["content"] for m in members), source="sleep:synthesis",
                                    type="factual", layer="long_term", tags=sorted({t for m in members for t in m["tags"]}),
                                    confidence=max(m["confidence"] for m in members),
                                    provenance={"origin": "sleep_synthesis", "learnedAt": self.clock(), "label": f"synthesized from {len(members)} memories"},
                                    derived_from=[m["id"] for m in members])
            self.ledger.log(merged["id"], "sleep_synthesize", self.actor, details={"sources": group})
            for m in members:
                self.store.delete(m["id"], "merged by sleep synthesis")
            synthesized += 1
            log.append(f"synthesized {merged['id']} from {', '.join(group)}")
        self.store.persist()
        return {"backupId": backup_id, "consolidated": len(plan["toConsolidate"]), "archived": len(plan["toArchive"]),
                "synthesized": synthesized, "actionLog": log}

    def restore(self, backup_id):
        b = self.backups[backup_id]
        self.store.restore_all(b["records"], b["seq"])
        self.ledger.log("*", "restore", self.actor, details={"backupId": backup_id})


class Dreaming:
    def __init__(self, store, ledger, clock, actor):
        self.store, self.ledger, self.clock, self.actor = store, ledger, clock, actor
        self.proposals, self.seq = {}, 0

    def _relatedness(self, a, b):
        return (0.5 * max(0.0, cosine(a["embedding"], b["embedding"])) + 0.2 * jaccard(a["tags"], b["tags"])
                + 0.1 * (1 if a["domain"] == b["domain"] else 0) + 0.2 * jaccard(a["entities"], b["entities"]))

    def _propose(self, out, **p):
        self.seq += 1
        prop = {**p, "id": f"dream-{self.seq}", "status": "proposed"}
        self.proposals[prop["id"]] = prop
        out.append(prop)
        self.ledger.log(prop["id"], "dream_proposed", self.actor, details={"type": p["type"], "derivedFrom": p["derivedFrom"]})

    def dream(self):
        out, recs, used = [], self.store.all(), set()
        clusters = []
        for seed in recs:
            if seed["id"] in used:
                continue
            group = [seed] + [o for o in recs if o["id"] != seed["id"] and o["id"] not in used and self._relatedness(seed, o) >= DEFAULTS["dreamRelatedness"]]
            if len(group) >= DEFAULTS["dreamClusterMinSize"]:
                used.update(g["id"] for g in group)
                clusters.append(group)
        for cluster in clusters[:DEFAULTS["maxDreamProposalsPerType"]]:
            domains = "/".join(sorted({m["domain"] for m in cluster}))
            self._propose(out, type="insight", content=f"Across {len(cluster)} related memories ({domains}): " + " + ".join(m["content"] for m in cluster),
                          derivedFrom=[m["id"] for m in cluster])
        n = 0
        for m in recs:
            if n >= DEFAULTS["maxDreamProposalsPerType"]:
                break
            if m["domain"] != "general":
                continue
            suggested = self.store.classify_domain(m["content"], m["tags"], m["type"])
            if suggested != "general":
                self._propose(out, type="domain", content=f'Reclassify "{m["content"][:60]}" as {suggested}', derivedFrom=[m["id"]], suggestedDomain=suggested)
                n += 1
        by_domain = {}
        for p in recs:
            if p["type"] in ("preference", "personal") or "event:user_correction" in p["tags"]:
                by_domain.setdefault(p["domain"], []).append(p)
        for domain, lst in list(by_domain.items())[:DEFAULTS["maxDreamProposalsPerType"]]:
            if len(lst) >= 2:
                self._propose(out, type="invariant", content=f"Stable pattern in {domain}: " + "; ".join(m["content"] for m in lst),
                              derivedFrom=[m["id"] for m in lst])
        return out

    def approve(self, proposal_id):
        p = self.proposals.get(proposal_id)
        if not p or p["status"] != "proposed":
            raise KeyError(f"H-MEM: no pending proposal {proposal_id}")
        p["status"] = "approved"
        self.ledger.log(proposal_id, "dream_approved", self.actor, details={"type": p["type"]})
        if p["type"] == "domain":
            for mid in p["derivedFrom"]:
                if self.store.get(mid):
                    self.store.update(mid, domain=p["suggestedDomain"])
            return None
        return self.store.add(content=p["content"], source="dreaming", type="factual" if p["type"] == "insight" else "preference",
                              layer="long_term", tags=[f"dream:{p['type']}"], confidence=0.75,
                              provenance={"origin": "dream", "learnedAt": self.clock(), "label": f"approved {p['type']} proposal"},
                              derived_from=p["derivedFrom"])

    def reject(self, proposal_id):
        p = self.proposals.get(proposal_id)
        if not p or p["status"] != "proposed":
            raise KeyError(f"H-MEM: no pending proposal {proposal_id}")
        p["status"] = "rejected"
        self.ledger.log(proposal_id, "dream_rejected", self.actor, details={"type": p["type"]})


class HMEM:
    def __init__(self, clock=None, persist_dir=None, actor="system"):
        import time
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.ledger = TrustLedger(self.clock, persist_dir)
        self.store = MemoryStore(self.clock, self.ledger, actor, persist_dir)
        self.retrieval = Retrieval(self.store, self.ledger, self.clock, actor)
        self.conflicts = Conflicts(self.store, self.ledger, self.clock, actor)
        self.sleep = Sleep(self.store, self.ledger, self.clock, actor)
        self.dreaming = Dreaming(self.store, self.ledger, self.clock, actor)

    def add(self, content, source, **kw):
        return self.store.add(content, source, **kw)

    def query(self, query, **kw):
        return self.retrieval.query(query, **kw)

    def feedback(self, mid, kind):
        self.retrieval.feedback(mid, kind)


# ----------------------------------------------------------------------------- PayProof wiring

PATTERN_LABELS = {
    "SK-LATE": "late-recorded cash event before cutoff (value date governs, P-4.2)",
    "SK-DUP": "duplicate payroll line or clawback posted twice",
    "SK-PREMISE": "claimant relied on CRM amount instead of the amended contract",
    "SK-PARTIAL": "collection basis caps the commissionable base",
    "SK-AMD": "amendment signed after cutoff excluded",
    "SK-POST": "financial event after cutoff excluded",
    "SK-EXC": "unapproved rate exception not applied",
    "SK-ID-AMBIG": "claimant identity cannot be uniquely linked to CRM",
    "SK-ID-NAME": "CRM name differs but email links the identity",
    "SK-SPLIT_TOTAL_INVALID": "split assignments do not total 100%",
    "SK-AMENDMENT_CONFLICT": "conflicting amendments on the same effective date",
    "SK-INJ": "embedded instruction in source text was quarantined",
}


def case_patterns(investigation: dict) -> list[str]:
    """Evidence-pattern tags of an investigation, derived from skeptic findings and blockers."""
    tags = set()
    for f in investigation["skeptic"]["findings"]:
        for prefix in PATTERN_LABELS:
            if f["id"] == prefix or f["id"].startswith(prefix + "-") or f["id"] == prefix.replace("SK-", "SK-"):
                tags.add(prefix)
    for b in investigation["calculation"]["blockers"]:
        tags.add("BLOCK-" + b["code"])
    return sorted(tags)


def pattern_query(patterns: list[str]) -> str:
    return " ".join(PATTERN_LABELS.get(p, p.replace("BLOCK-", "").replace("_", " ").lower()) for p in patterns) + " " + " ".join(p.lower() for p in patterns)


class PrecedentMemory:
    """Verified-precedent memory for PayProof on top of H-MEM.

    Write rule: only a human-approved action whose postcondition was verified becomes a precedent.
    Read rule: a case never retrieves its own precedents; retrieval only informs the reviewer."""

    SOURCE_PREFIX = "payproof:verified-action:"

    def __init__(self, persist_dir=None, clock=None):
        self.hmem = HMEM(clock=clock, persist_dir=persist_dir, actor="payproof")

    def record_verified(self, investigation: dict, action: dict) -> dict | None:
        if action.get("state") != "VERIFIED" or not (action.get("receipt") or {}).get("postcondition", {}).get("passed"):
            return None  # unverified outcomes never become trusted memory
        patterns = case_patterns(investigation)
        if not patterns:
            return None
        case_id = investigation["case_id"]
        for m in self.hmem.store.all():
            if m.get("missionId") == case_id and m["source"] == self.SOURCE_PREFIX + action["id"]:
                return m  # idempotent per action
        content = (f"Precedent {case_id}: " + "; ".join(PATTERN_LABELS.get(p, p) for p in patterns)
                   + f". Outcome: {investigation['proof_status']} / {investigation['verdict']}; "
                   f"action {action['type']} approved by {action['approved_by']} and verified.")
        return self.hmem.add(content, self.SOURCE_PREFIX + action["id"], type="factual", layer="long_term",
                             tags=["project:payproof"] + patterns + [f"verdict:{investigation['verdict']}", f"action:{action['type']}"],
                             confidence=0.8, mission_id=case_id,
                             provenance={"origin": "plan_completion", "learnedAt": self.hmem.clock(), "label": "verified PayProof action",
                                         "refs": [case_id, action["id"], action["receipt"]["receipt_id"], investigation["proof_hash"]]})

    def recall(self, investigation: dict, top_n: int = 3) -> dict:
        patterns = case_patterns(investigation)
        own = investigation["case_id"]
        if not patterns:
            return {"patterns": [], "precedents": [], "trace": None}
        res = self.hmem.query(pattern_query(patterns), top_n=top_n, threshold=0.2,
                              where=lambda m: m.get("missionId") != own and m["source"].startswith(self.SOURCE_PREFIX))
        out = []
        for it in res["memories"]:
            m = it["memory"]
            shared = sorted(set(patterns) & set(m["tags"]))
            verdict = next((t.split(":", 1)[1] for t in m["tags"] if t.startswith("verdict:")), None)
            act = next((t.split(":", 1)[1] for t in m["tags"] if t.startswith("action:")), None)
            out.append({"memory_id": m["id"], "case_id": m["missionId"], "relevance": round(it["relevance"], 4),
                        "shared_patterns": shared, "verdict": verdict, "action": act, "content": m["content"],
                        "refs": m["provenance"].get("refs", []), "confidence": m["confidence"],
                        "consistent": act == investigation["proposed_action"]["type"] if shared else None})
        return {"patterns": patterns, "precedents": out, "trace": res["trace"]}
