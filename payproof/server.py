"""PayProof HTTP API + Decision Room static UI. Standard library only.

Run: python3 -m payproof.server   (PORT env var, default 8360)
"""

import json
import os
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .actions import USERS, ActionError, ActionService, late_credit_note
from .consumer_intake import ConsumerIntakeError, claim_from_form
from .consumer_sources import make_consumer_source, now_iso, unfiled_bookings
from .integrations import integration_status, record_investigation
from .intake import IntakeError, create_case, template_from_case
from .money import D, fmt
from .reclaim_actions import ConsumerActionService
from .reclaim_bridge import DOMAINS, ReclaimBridgeClient, ReclaimBridgeError, bridge_status, text_pdf
from .reclaim_evidence import ConsumerEvidenceIndex
from .reclaim_policy import load_rulebook
from .reclaim_verifier import what_if
from .scout import ScoutError
from .sources import make_source, load_plans

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DOCS = ROOT / "docs"
STATIC_ROOTS = {"/deck": DOCS / "deck.html"}  # exact paths
STATIC_DIRS = {"/img/": DOCS / "img"}  # prefixes
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
        ".png": "image/png", ".pdf": "application/pdf", ".mp4": "video/mp4"}
BENCH_LOCK = threading.Lock()


class App:
    def __init__(self, source=None, audit_path="default", consumer_source=None):
        self.source = source or make_source()
        self.plans = load_plans()
        mem = ROOT / "var" / "hmem" if audit_path == "default" else None
        self.svc = ActionService(self.source, self.plans, memory_dir=mem) if audit_path == "default" else \
            ActionService(self.source, self.plans, audit_path=audit_path)
        self.cache = {}
        self.reclaim = ReclaimBridgeClient()
        self.rulebook = load_rulebook()
        cvar = ROOT / "var" / "consumer" if audit_path == "default" else None
        self.consumer_source = consumer_source or make_consumer_source(var_dir=cvar)
        self.consumer = ConsumerActionService(self.consumer_source, self.rulebook, self.svc.scout, memory=self.svc.memory,
                                              bridge=self.reclaim, var_dir=cvar)

    def investigation(self, case_id):
        return self.svc.investigate(case_id)

    # ------------------------------------------------------------------ consumer disputes (RECLAIM x PayProof)
    def consumer_queue(self, user):
        rows = []
        for cid in self.consumer.visible_cases(user):
            try:
                r = self.consumer.investigate(cid, user, use_model=False)
            except ActionError:
                continue
            r.pop("_world", None)
            acts = self.consumer.for_case(cid)
            a, d = r["proposed_action"], r["dispute"]
            rows.append({"case_id": cid, "domain": r["domain"], "kind": "consumer", "title": r["title"], "claimant": d["claimant_name"],
                         "institution": r["institution_name"], "tenant_id": r["tenant_id"],
                         "claimed": fmt(D(d.get("claimed_refund") or 0) + D(d.get("claimed_compensation") or 0)),
                         "owed": r["calculation"]["delta"], "proof_status": r["proof_status"], "verdict": r["verdict"],
                         "action": a["type"], "amount": a["amount"], "escalated": bool(a.get("escalated")),
                         "action_state": acts[-1]["state"] if acts else None,
                         "hypothesis": r["hypotheses"][0]["status"] if r["hypotheses"] else None,
                         "reclaim_linked": bool((r.get("reclaim") or {}).get("case_id")), "filed_at": d["filed_at"][:10],
                         "tags": r["tags"]})
        return rows

    def consumer_report(self, case_id, user, use_model=True):
        r = self.consumer.investigate(case_id, user, use_model=use_model)
        r.pop("_world", None)
        r["actions"] = [{k: v for k, v in a.items() if k != "contracts"} for a in self.consumer.for_case(case_id)]
        r["history"] = self.consumer.history.get(case_id, [])
        record_investigation(case_id, {
            "run_id": r["run_id"], "world_model": r["world_model"]["entities"] > 0,
            "hmem": {"patterns": len(r["precedents"]["patterns"]), "precedents": len(r["precedents"]["precedents"])},
            "scout": {"records_scanned": len(r["lineage"]), "quarantined": len(r["security"]["quarantined"])},
            "zetaris": sorted(k for k, v in r["sources_meta"]["provenance"].items() if str(v).startswith("zetaris")) or False,
            "nemotron": any(m["status"] == "ok" for m in r["telemetry"]["model_calls"]),
            "reclaim": bool((r.get("reclaim") or {}).get("case_id"))})
        return r

    def _consumer_contract(self, intent, user, capability, case_id):
        try:
            c = self.svc.scout.decide(intent, user, params={"case_id": case_id})
            self.svc.scout.verify(c, capability, intent=intent, user_id=user["id"])
        except ScoutError as e:
            self.consumer.audit.append("DENIED", user["id"], op=intent, reason=e.code, case_id=case_id)
            raise ActionError("FORBIDDEN" if e.code == "POLICY_BLOCK" else e.code, e.message, e.status)

    def link_reclaim(self, case_id, user):
        """File the claim into RECLAIM under the tenant's principal, upload its documents to the RECLAIM vault
        (as PDFs) and adopt the vault's extracted text as the evidence. Idempotent per case."""
        case = self.consumer.load_visible(case_id, user)
        self._consumer_contract("consumer.file", user, "reclaim.case.create", case_id)
        claim = self.consumer_source.load_claim(case_id)
        if (claim.get("reclaim") or {}).get("case_id"):
            return claim["reclaim"]
        tenant, d = case["tenant_id"], case["dispute"]
        summary = (f"{d.get('narrative', '')} Booking {d.get('booking_ref')} on flight {d.get('flight_no')}. Claimed refund INR "
                   f"{d.get('claimed_refund')} and compensation INR {d.get('claimed_compensation')}. Filed via PayProof {case_id}.")
        rc = self.reclaim.create_case(tenant, case["title"], case["institution_name"], summary,
                                      case["domain"] if case["domain"] in DOMAINS else "airlines", case.get("jurisdiction", "IN"))
        uploaded = []
        for doc in claim.get("documents", []):
            up = self.reclaim.upload_document(tenant, rc["id"], f"{doc['id']}.pdf", text_pdf(doc.get("text", ""), doc.get("title", "")))
            uploaded.append({"local_id": doc["id"], "document_id": up["document_id"], "extraction_method": up.get("extraction_method"),
                             "text_chars": up.get("text_chars")})
        vault = {x.get("document_id") or x.get("id"): x for x in self.reclaim.list_documents(tenant, rc["id"])}
        for doc in claim.get("documents", []):  # the evidence now comes from the RECLAIM vault's extracted text
            u = next((x for x in uploaded if x["local_id"] == doc["id"]), None)
            row = vault.get(u["document_id"]) if u else None
            if row and row.get("text_extract"):
                doc.update(text=row["text_extract"], provenance="reclaim-document-vault", reclaim_document_id=u["document_id"],
                           retrieved_at=now_iso())
        claim["reclaim"] = {"case_id": rc["id"], "status": rc["status"], "linked_at": now_iso(), "linked_by": user["id"],
                            "documents": uploaded}
        self.consumer_source.save_claim(claim)
        try:
            ev = self.reclaim.add_event(tenant, rc["id"], "payproof_linked", f"Linked to PayProof {case_id}",
                                        f"{len(uploaded)} document(s) uploaded for independent verification")
            claim["reclaim"]["link_event_id"] = ev["id"]
            self.consumer_source.save_claim(claim)
        except ReclaimBridgeError:
            pass  # the link stands; the timeline note is a convenience
        self.consumer.audit.append("RECLAIM_LINKED", user["id"], case_id=case_id, tenant=tenant, reclaim_case_id=rc["id"],
                                   documents=len(uploaded))
        return claim["reclaim"]

    def run_reclaim_agents(self, case_id, user):
        self.consumer.load_visible(case_id, user)
        self._consumer_contract("consumer.agents", user, "reclaim.agents.run", case_id)
        claim = self.consumer_source.load_claim(case_id)
        link = claim.get("reclaim") or {}
        if not link.get("case_id"):
            raise ActionError("NOT_LINKED", "link the case to RECLAIM before running its agents", 409)
        run = self.reclaim.run_agents(claim["tenant_id"], link["case_id"])
        claim.setdefault("agent_runs", []).append({k: run.get(k) for k in ("provenance", "run_at", "status", "workflow_engine", "llm_call_count")})
        claim["agent_run"] = run
        self.consumer_source.save_claim(claim)
        self.consumer.audit.append("RECLAIM_AGENTS_RUN", user["id"], case_id=case_id, tenant=claim["tenant_id"],
                                   reclaim_case_id=link["case_id"], citations=len(run["citations"]))
        return run

    def file_consumer_case(self, body, user):
        if "consumer.file" not in user["perms"]:
            raise ActionError("FORBIDDEN", f"role {user['role']} cannot file consumer disputes", 403)
        texts = {k: v for k, v in body.items() if isinstance(v, str)}
        for i, doc in enumerate(body.get("documents") or []):
            if isinstance(doc, dict) and isinstance(doc.get("text"), str):
                texts[f"documents[{i}].text"] = doc["text"]
        try:  # Meterless Scout guard: embedded instructions in claimant text are refused outright
            self.svc.scout.decide("consumer.file", user, texts=texts)
        except ScoutError as e:
            self.consumer.audit.append("DENIED", user["id"], op="consumer.file", reason=e.code)
            raise ActionError(e.code, e.message, e.status)
        bookings = [b for b in self.consumer_source.lake.get("airline_pss", []) if b.get("type") == "booking"]
        try:
            claim = claim_from_form(body, user, bookings)
        except ConsumerIntakeError as e:
            raise ActionError("INVALID_INPUT", str(e), 422)
        case = self.consumer_source.create_case(claim)
        self.consumer.audit.append("CONSUMER_CASE_FILED", user["id"], case_id=case["case_id"], tenant=case["tenant_id"],
                                   booking_ref=case["dispute"]["booking_ref"])
        out = {"case_id": case["case_id"]}
        if body.get("link_reclaim"):
            try:
                out["reclaim"] = self.link_reclaim(case["case_id"], user)
            except ReclaimBridgeError as e:
                out["reclaim"] = {"linked": False, "error": e.code, "message": e.message}
        r = self.consumer_report(case["case_id"], user, use_model=False)
        out.update(proof_status=r["proof_status"], verdict=r["verdict"], action=r["proposed_action"]["type"],
                   amount=r["proposed_action"]["amount"])
        return out

    def overview(self, user):
        consumer = self.consumer_queue(user)
        payroll = self.queue(user) if ("case.view" in user["perms"] or user["role"] == "sales_rep") else []
        integ = integration_status()
        pending = [{"id": a["id"], "domain": "payroll", "case_id": a["case_id"], "type": a["type"], "amount": a.get("amount"),
                    "required_permission": a["required_permission"]} for a in self.svc.actions.values()
                   if a["state"] == "AWAITING_APPROVAL" and "case.view" in user["perms"]]
        pending += [{"id": a["id"], "domain": "consumer", "case_id": a["case_id"], "type": a["type"], "amount": a.get("amount"),
                     "required_permission": a["required_permission"]} for a in self.consumer.actions.values()
                    if a["state"] == "AWAITING_APPROVAL" and a.get("tenant_id") == user.get("tenant")]

        def counts(rows, key):
            out = {}
            for r in rows:
                out[r[key]] = out.get(r[key], 0) + 1
            return dict(sorted(out.items()))
        by_key = {r["key"]: r for r in integ["rows"]}
        agents = [("RECLAIM specialist agents", "reclaim"), ("Zetaris federation", "zetaris"), ("Meterless World Model", "world_model"),
                  ("Meterless Scout guard", "scout"), ("Meterless H-MEM precedents", "hmem"), ("NVIDIA Nemotron narrator", "nemotron")]
        return {"totals": {"investigations": len(consumer) + len(payroll), "consumer": len(consumer), "payroll": len(payroll),
                           "pending_approvals": len(pending)},
                "consumer_status": counts(consumer, "proof_status"), "consumer_actions": counts(consumer, "action"),
                "payroll_status": counts(payroll, "proof_status"), "pending_approvals": pending,
                "agent_health": [{"agent": name, "key": k, "state": by_key[k]["state"], "detail": by_key[k]["detail"]} for name, k in agents]
                + [{"agent": "Deterministic policy engine", "key": "policy", "state": "LIVE",
                    "detail": f"rulebook {self.rulebook['rulebook_version']} ({len(self.rulebook['rules'])} rules) + payroll plans"},
                   {"agent": "Independent skeptic + verifier", "key": "skeptic", "state": "LIVE",
                    "detail": "re-query, independent recompute, citation and amount challenge on every run"}],
                "sponsors": [{k: r.get(k) for k in ("sponsor", "short", "key", "state", "connectivity", "last_success", "detail")}
                             for r in integ["rows"]],
                "latest_investigation": integ["latest_investigation"], "tenant": user.get("tenant")}

    def queue(self, user, domain_filter=None):
        payroll_cases = []
        for cid in self.source.list_case_ids():
            r = self.svc.investigate(cid, use_model=False)
            if user and user["role"] == "sales_rep" and r["dispute"]["employee_id"] != user["id"]:
                continue
            acts = [a for a in self.svc.actions.values() if a["case_id"] == cid]
            emp = next(n for n in r["graph"]["nodes"] if n["id"] == r["dispute"]["employee_id"])
            verified = r["proof_status"] == "VERIFIED"
            exposure = abs(float(r["calculation"]["delta"])) if verified else float(r["dispute"]["claimed_shortfall"])
            payroll_cases.append({"case_id": cid, "domain": "payroll", "kind": "payroll", "title": r["title"], "claimant": emp["label"], "employee_id": r["dispute"]["employee_id"],
                        "claimed": r["dispute"]["claimed_shortfall"], "delta": r["calculation"]["delta"] if verified else None,
                        "exposure": f"{exposure:.2f}", "proof_status": r["proof_status"], "verdict": r["verdict"],
                        "action": r["proposed_action"]["type"], "action_state": acts[-1]["state"] if acts else None,
                        "filed_at": r["dispute"]["filed_at"], "tags": r["tags"]})
        payroll_cases.sort(key=lambda x: (0 if "demo" in x["tags"] else 1 if "user-filed" in x["tags"] else 2,
                                -int(x["case_id"][5:]) if "user-filed" in x["tags"] else 0, -float(x["exposure"])))

        if domain_filter == "consumer":
            return self.consumer_queue(user)
        elif domain_filter == "all":
            return payroll_cases + self.consumer_queue(user)
        return payroll_cases



LOGS = ROOT / "logs"


def write_logs(r, world):
    """Judge-inspectable traces: the run summary and the Meterless World Model audit as JSONL."""
    from .world_model import write_audit_jsonl
    LOGS.mkdir(exist_ok=True)
    write_audit_jsonl(world, LOGS / f"{r['run_id']}-world-model.jsonl")
    trace = {k: r[k] for k in ("run_id", "case_id", "proof_status", "verdict", "proof_hash", "source_fingerprint",
                               "world_model_state_hash", "telemetry")}
    trace["action"] = {k: r["proposed_action"][k] for k in ("type", "amount", "required_permission", "idempotency_key")}
    trace["skeptic_strongest"] = r["skeptic"]["strongest"]
    trace["invariants"] = r["verification"]["invariants"]
    with (LOGS / f"{r['run_id']}-trace.jsonl").open("a") as fh:
        fh.write(json.dumps(trace, default=str) + "\n")


def log(**kw):
    sys.stderr.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **kw}) + "\n")


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        server_version = "PayProof/1.0"

        def log_message(self, *a):
            pass

        def _send(self, status, body, ctype="application/json", filename=None):
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("X-Request-ID", self._rid)
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 10_000:
                raise ActionError("TOO_LARGE", "request body too large", 413)
            if not n:
                return {}
            try:
                body = json.loads(self.rfile.read(n))
            except json.JSONDecodeError:
                raise ActionError("BAD_JSON", "invalid JSON body", 400)
            if not isinstance(body, dict):
                raise ActionError("BAD_JSON", "body must be an object", 400)
            return body

        def _token(self):
            return self.headers.get("X-Demo-User", "")

        def _viewer(self):
            u = USERS.get(self._token())
            if not u:
                raise ActionError("UNAUTHENTICATED", "select a demo user (X-Demo-User)", 401)
            return u

        def _check_case_access(self, user, case_id):
            if user["role"] == "sales_rep":
                case = app.source.load_case(case_id)
                if case["dispute"]["employee_id"] != user["id"]:
                    raise ActionError("FORBIDDEN", "sales reps may only view their own disputes", 403)

        def _route(self, method):
            path = urlparse(self.path).path
            if method == "GET" and not path.startswith("/api/"):
                return self._static(path)
            m = lambda pat: re.fullmatch(pat, path)
            if method == "GET" and path == "/api/health":
                return 200, {"ok": True}
            if method == "GET" and path == "/api/integrations":
                return 200, integration_status()
            if method == "POST" and path == "/api/integrations/check":
                u = self._viewer()
                from .diagnostics import run_live_check
                result = run_live_check(app)
                app.svc.audit.append("INTEGRATION_CHECK", u["id"], ok=[c["key"] for c in result["checks"] if c["ok"]])
                return 200, result
            if method == "GET" and path == "/api/users":
                return 200, [{"token": t, **{k: v for k, v in u.items() if k != "perms"}, "perms": sorted(u["perms"])}
                             for t, u in USERS.items()]
            if method == "GET" and path == "/api/cases":
                q = parse_qs(urlparse(self.path).query)
                dom = q.get("domain", [None])[0]
                return 200, app.queue(self._viewer(), domain_filter=dom)
            # ---------------------------------------------------------- RECLAIM x PayProof (consumer disputes)
            if method == "GET" and path == "/api/reclaim/status":
                u = self._viewer()
                return 200, {"bridge": bridge_status(), "ping": app.reclaim.ping(u["tenant"])}
            if method == "GET" and path == "/api/overview":
                return 200, app.overview(self._viewer())
            if method == "GET" and path == "/api/sponsors":
                self._viewer()
                rb = app.rulebook
                return 200, {**integration_status(), "consumer_source": app.consumer_source.name,
                             "rulebook": {"version": rb["rulebook_version"], "as_of": rb["as_of"], "rules": len(rb["rules"]),
                                          "disclaimer": rb["_disclaimer"]}}
            if method == "GET" and path == "/api/consumer/cases":
                return 200, app.consumer_queue(self._viewer())
            if method == "GET" and path == "/api/consumer/bookings":
                self._viewer()
                return 200, unfiled_bookings()
            if method == "POST" and path == "/api/consumer/cases":
                return 201, app.file_consumer_case(self._body(), self._viewer())
            if method == "GET" and path == "/api/consumer/audit":
                u = self._viewer()
                if "case.view" not in u["perms"]:
                    raise ActionError("FORBIDDEN", f"role {u['role']} cannot read the audit trail", 403)
                mine = set(app.consumer.visible_cases(u)) | {a["id"] for a in app.consumer.actions.values() if a.get("tenant_id") == u["tenant"]}
                ents = [e for e in app.consumer.audit.entries
                        if e["details"].get("tenant") == u["tenant"] or e["details"].get("case_id") in mine
                        or e["details"].get("action_id") in mine]
                return 200, {"chain_valid": app.consumer.audit.verify_chain(), "entries": ents[-200:], "total": len(app.consumer.audit.entries)}
            cid_re = r"/api/consumer/cases/(CDX-\d{4})"
            if (g := m(cid_re)) and method == "GET":
                return 200, app.consumer_report(g[1], self._viewer())
            if (g := m(cid_re + "/evidence")) and method == "GET":
                r = app.consumer.latest(g[1], self._viewer())
                return 200, {k: r[k] for k in ("case_id", "run_id", "source_fingerprint", "lineage", "data_quality", "doc_facts", "documents",
                                               "contradictions", "claims", "sources_meta", "agent", "dispute")}
            if (g := m(cid_re + "/verify")) and method == "POST":
                u = self._viewer()
                r = app.consumer_report(g[1], u)
                link = r.get("reclaim") or {}
                if link.get("case_id"):
                    try:
                        app.reclaim.add_event(r["tenant_id"], link["case_id"], "payproof_verification",
                                              f"PayProof verification: {r['proof_status']} / {r['proposed_action']['type']}",
                                              f"run {r['run_id']}; proof {r['proof_hash'][:16]}; owed {r['calculation']['delta']}")
                        r["reclaim_mirror"] = {"mirrored": True}
                    except ReclaimBridgeError as e:
                        r["reclaim_mirror"] = {"mirrored": False, "reason": e.code}
                return 200, r
            if (g := m(cid_re + "/explanation")) and method == "GET":
                r = app.consumer.latest(g[1], self._viewer())
                return 200, {"case_id": r["case_id"], "run_id": r["run_id"], "explanation": r["explanation"], "hypotheses": r["hypotheses"],
                             "citations": r["agent"]["citations"], "validation": r["validation"], "telemetry": r["telemetry"]}
            if (g := m(cid_re + "/trace")) and method == "GET":
                r = app.consumer.latest(g[1], self._viewer())
                return 200, {"case_id": r["case_id"], "run_id": r["run_id"], "trace": r["trace"], "telemetry": r["telemetry"],
                             "world_model": r["world_model"], "verification": r["verification"],
                             "skeptic": {k: r["skeptic"][k] for k in ("rechecks", "independent_recompute", "agreement", "unchecked")},
                             "history": app.consumer.history.get(g[1], [])}
            if (g := m(cid_re + "/counterfactual")) and method == "POST":
                case = app.consumer.load_visible(g[1], self._viewer())
                try:
                    return 200, what_if(ConsumerEvidenceIndex(case, app.rulebook), app.rulebook, self._body())
                except (ValueError, TypeError) as e:
                    raise ActionError("BAD_REQUEST", str(e), 400)
            if (g := m(cid_re + "/reclaim/link")) and method == "POST":
                return 200, app.link_reclaim(g[1], self._viewer())
            if (g := m(cid_re + "/reclaim/agents")) and method == "POST":
                return 200, app.run_reclaim_agents(g[1], self._viewer())
            if (g := m(cid_re + "/reclaim/timeline")) and method == "GET":
                case = app.consumer.load_visible(g[1], self._viewer())
                link = case.get("reclaim") or {}
                if not link.get("case_id"):
                    raise ActionError("NOT_LINKED", "case is not linked to RECLAIM", 409)
                return 200, {"reclaim_case_id": link["case_id"], "events": app.reclaim.timeline(case["tenant_id"], link["case_id"])}
            if (g := m(cid_re + "/simulate/source-change")) and method == "POST":
                u = self._viewer()
                if not ({"action.propose", "action.approve"} & u["perms"]):
                    raise ActionError("FORBIDDEN", f"role {u['role']} cannot simulate source changes", 403)
                kind = self._body().get("kind", "refund_credit")
                r = app.consumer.latest(g[1], u)
                calc, n = r["calculation"], len(app.consumer_source.overlays.get(g[1], [])) + 1
                if kind == "refund_credit" and calc.get("payment_id") and calc.get("refund_due"):
                    owed = fmt(max(D(calc["refund_due"]) - D(calc["refund_received"]), D("0.01")))
                    system, rec = "payments", {"id": f"CRD-LATE-{g[1][4:]}-{n}", "type": "card_credit", "payment_id": calc["payment_id"],
                                               "kind": "refund", "amount": owed, "posted_at": r["sources_meta"]["feeds"]["payments"].get("as_of")
                                               or now_iso(), "descriptor": "late-posted refund", "recorded_at": now_iso()}
                elif kind == "carrier_refund" and calc.get("booking_id"):
                    system, rec = "airline_pss", {"id": f"ARF-LATE-{g[1][4:]}-{n}", "type": "airline_refund", "booking_id": calc["booking_id"],
                                                  "amount": calc.get("refund_due") or "0.00", "mode": "original_instrument", "status": "PROCESSED",
                                                  "processed_at": "2026-09-01T00:00:00Z", "note": "late carrier refund claim",
                                                  "recorded_at": now_iso()}
                else:
                    raise ActionError("BAD_REQUEST", "kind must be refund_credit or carrier_refund, on a case with booking and payment", 400)
                app.consumer_source.inject_late_event(g[1], system, rec)
                app.consumer.audit.append("SIM_SOURCE_CHANGE", u["id"], case_id=g[1], tenant=u["tenant"], record_id=rec["id"])
                return 201, {"injected": rec, "system": system, "hypothetical": False, "note": "Simulated late-arriving source record",
                             "revalidation": app.consumer.revalidate(g[1], u)}
            if (g := m(cid_re + "/revalidate")) and method == "POST":
                return 200, app.consumer.revalidate(g[1], self._viewer())
            if (g := m(cid_re + "/actions")) and method == "POST":
                return 201, app.consumer.propose(g[1], self._viewer())
            aid_re = r"/api/consumer/actions/(CACT-[0-9a-f]{10})"
            if (g := m(aid_re)) and method == "GET":
                return 200, app.consumer.get(g[1], self._viewer())
            if (g := m(aid_re + "/decision")) and method == "POST":
                u, b = self._viewer(), self._body()
                if b.get("decision") not in ("approve", "reject"):
                    raise ActionError("BAD_REQUEST", "decision must be approve|reject", 400)
                return 200, app.consumer.decide(g[1], u, b["decision"] == "approve", str(b.get("note", "")))
            if (g := m(aid_re + "/escalate")) and method == "POST":
                u, b = self._viewer(), self._body()
                return 200, app.consumer.escalate(g[1], u, str(b.get("note", "")))
            if (g := m(aid_re + "/execute")) and method == "POST":
                return 200, app.consumer.execute(g[1], self._viewer(), self.headers.get("Idempotency-Key", ""))
            if method == "POST" and path == "/api/consumer/sim/fail-next":
                u = self._viewer()
                if "action.execute" not in u["perms"]:
                    raise ActionError("FORBIDDEN", f"role {u['role']} cannot inject failures", 403)
                app.consumer.sandbox.fail_next = True
                app.consumer.audit.append("SIM_FAIL_NEXT", u["id"], tenant=u["tenant"])
                return 200, {"fail_next": True}

            if (g := m(r"/api/cases/(CASE-\d{4})")) and method == "GET":
                self._check_case_access(self._viewer(), g[1])
                r = app.investigation(g[1])
                world = r.pop("_world")
                write_logs(r, world)
                r["precedents"] = app.svc.memory.recall(r)  # Meterless H-MEM; never alters the proof
                prov = r["sources_meta"]["provenance"]
                record_investigation(g[1], {
                    "run_id": r["run_id"], "world_model": r["world_model"]["entities"] > 0,
                    "hmem": {"patterns": len(r["precedents"]["patterns"]), "precedents": len(r["precedents"]["precedents"])},
                    "scout": {"records_scanned": sum(len(b["records"]) for b in app.source.load_case(g[1])["sources"].values()),
                              "quarantined": len(r["security"]["quarantined"])},
                    "zetaris": sorted(k for k, v in prov.items() if v.startswith("zetaris")) or False,
                    "nemotron": any(m["status"] == "ok" for m in r["telemetry"]["model_calls"])})
                r["actions"] = [a for a in app.svc.actions.values() if a["case_id"] == g[1]]
                return 200, r
            if (g := m(r"/api/cases/(CASE-\d{4})/dossier")) and method == "GET":
                self._check_case_access(self._viewer(), g[1])
                r = app.investigation(g[1])
                r.pop("_world", None)
                r["precedents"] = app.svc.memory.recall(r)
                acts = [a for a in app.svc.actions.values() if a["case_id"] == g[1]]
                dossier = {"dossier_version": 1, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "disclaimer": "Evidence-backed recommendation for authorized human review. Not a binding financial decision. Synthetic data.",
                           "case_id": g[1], "decision": {k: r[k] for k in ("proof_status", "verdict", "proposed_action")},
                           "calculation": r["calculation"], "bundle": r["bundle"], "skeptic": r["skeptic"],
                           "counterfactuals": r["counterfactuals"], "verification": r["verification"], "security": r["security"],
                           "precedents": r["precedents"], "trace": r["trace"], "provenance": {k: r[k] for k in
                           ("run_id", "proof_hash", "source_fingerprint", "world_model_state_hash", "engine_version", "plan_version")},
                           "sources_meta": r["sources_meta"], "actions": [{k: v for k, v in a.items() if k != "contracts"} for a in acts],
                           "audit": [e for e in app.svc.audit.entries if e["details"].get("case_id") == g[1]
                                     or e["details"].get("action_id") in {a["id"] for a in acts}]}
                return 200, (json.dumps(dossier, indent=2, default=str).encode(), "application/json", f"payproof-dossier-{g[1]}.json")
            if (g := m(r"/api/cases/(CASE-\d{4})/sources")) and method == "GET":
                self._check_case_access(self._viewer(), g[1])
                return 200, app.source.load_case(g[1])
            if (g := m(r"/api/cases/(CASE-\d{4})/actions")) and method == "POST":
                return 201, app.svc.propose(g[1], self._token())
            if (g := m(r"/api/actions/(ACT-[0-9a-f]{10})")) and method == "GET":
                self._viewer()
                return 200, app.svc.get(g[1])
            if (g := m(r"/api/actions/(ACT-[0-9a-f]{10})/decision")) and method == "POST":
                b = self._body()
                if b.get("decision") not in ("approve", "reject"):
                    raise ActionError("BAD_REQUEST", "decision must be approve|reject", 400)
                return 200, app.svc.decide(g[1], self._token(), b["decision"] == "approve", str(b.get("note", "")))
            if (g := m(r"/api/actions/(ACT-[0-9a-f]{10})/escalate")) and method == "POST":
                b = self._body()
                return 200, app.svc.escalate(g[1], self._token(), str(b.get("note", "")))
            if (g := m(r"/api/actions/(ACT-[0-9a-f]{10})/execute")) and method == "POST":
                return 200, app.svc.execute(g[1], self._token(), self.headers.get("Idempotency-Key", ""))
            if (g := m(r"/api/cases/(CASE-\d{4})/simulate/late-event")) and method == "POST":
                u = self._viewer()
                case = app.source.load_case(g[1])
                inv = next((r for r in case["sources"]["billing"]["records"] if r["type"] == "invoice"), None)
                if not inv:
                    raise ActionError("BAD_REQUEST", "case has no invoice to attach a credit note to", 400)
                rec = late_credit_note(g[1], len(case.get("late_events", [])) + 1)
                rec["invoice_id"] = inv["id"]
                app.source.inject_late_event(g[1], "billing", rec)
                app.svc.audit.append("SIM_LATE_EVENT", u["id"], case_id=g[1], record_id=rec["id"])
                return 201, {"injected": rec, "hypothetical": False, "note": "Simulated late-arriving source record"}
            if method == "POST" and path == "/api/sim/fail-next":
                u = self._viewer()
                app.svc.adapter.fail_next = True
                app.svc.audit.append("SIM_FAIL_NEXT", u["id"])
                return 200, {"fail_next": True}
            if method == "POST" and path == "/api/demo/reset":
                self._viewer()
                app.svc.reset()
                app.consumer.reset()
                return 200, {"reset": True}
            if method == "GET" and path == "/api/audit":
                self._viewer()
                return 200, {"chain_valid": app.svc.audit.verify_chain(), "entries": app.svc.audit.entries[-200:]}
            if method == "GET" and path == "/api/benchmark":
                p = ROOT / "bench" / "results" / "latest.json"
                return (200, json.loads(p.read_text())) if p.exists() else (404, {"error": "run python3 -m payproof.bench"})
            if method == "POST" and path == "/api/benchmark/run":
                u = self._viewer()
                if "benchmark.run" not in u["perms"]:
                    raise ActionError("FORBIDDEN", f"role {u['role']} cannot run the benchmark", 403)
                if not BENCH_LOCK.acquire(blocking=False):
                    raise ActionError("BUSY", "a benchmark run is already in progress", 409)
                try:
                    from .bench import run as run_bench
                    gt = json.loads((ROOT / "bench" / "ground_truth.json").read_text())["cases"]
                    report = run_bench(sorted(gt), write=True)
                finally:
                    BENCH_LOCK.release()
                app.svc.audit.append("BENCHMARK_RUN", u["id"], cases=report["sample_size"],
                                     correct=report["agent"]["decisions_correct"])
                return 200, report
            if method == "GET" and path == "/api/intake/template":
                self._viewer()
                q = parse_qs(urlparse(self.path).query)
                base = q.get("from", [app.source.list_case_ids()[0]])[0]
                return 200, {"from": base, "form": template_from_case(app.source.load_case(base))}
            if method == "POST" and path == "/api/cases":
                u = self._viewer()
                if "case.file" not in u["perms"]:
                    raise ActionError("FORBIDDEN", f"role {u['role']} cannot file disputes", 403)
                body = self._body()
                try:  # Meterless Scout guard on user-supplied free text: embedded instructions are refused
                    app.svc.scout.decide("dispute.file", u, texts={k: v for k, v in body.items()
                                                                   if k in ("title", "narrative", "account", "rep_name", "crm_name", "co_seller_name")
                                                                   and isinstance(v, str)})
                except ScoutError as e:
                    app.svc.audit.append("DENIED", u["id"], op="dispute.file", reason=e.code)
                    raise ActionError(e.code, e.message, e.status)
                try:
                    case = create_case(body, set(app.source.list_case_ids()), directory=app.source.user_dir)
                except IntakeError as e:
                    raise ActionError("INVALID_INPUT", str(e), 422)
                app.svc.audit.append("CASE_FILED", u["id"], case_id=case["case_id"],
                                     claimed=case["dispute"]["claimed_shortfall"])
                r = app.svc.investigate(case["case_id"], use_model=False)
                return 201, {"case_id": case["case_id"], "proof_status": r["proof_status"], "verdict": r["verdict"],
                             "action": r["proposed_action"]["type"], "due": r["calculation"]["due"] if r["proof_status"] == "VERIFIED" else None}
            return 404, {"error": "not found"}

        def _static(self, path):
            base, rel = WEB, ("index.html" if path in ("/", "") else path.lstrip("/"))
            if path in STATIC_ROOTS:
                base, rel = STATIC_ROOTS[path].parent, STATIC_ROOTS[path].name
            for prefix, d in STATIC_DIRS.items():
                if path.startswith(prefix):
                    base, rel = d, path[len(prefix):]
            f = (base / rel).resolve()
            if not str(f).startswith(str(base.resolve()) + os.sep) or not f.is_file():
                return 404, {"error": "not found"}
            return 200, (f.read_bytes(), MIME.get(f.suffix, "application/octet-stream"))

        def _handle(self, method):
            t0 = time.monotonic()
            hdr = self.headers.get("X-Request-ID", "")
            self._rid = hdr if re.fullmatch(r"[A-Za-z0-9._-]{8,64}", hdr) else uuid.uuid4().hex[:16]  # correlation id
            try:
                status, body = self._route(method)
            except ActionError as e:
                status, body = e.status, {"error": e.code, "message": e.message}
            except ReclaimBridgeError as e:  # upstream failures are reported as such, never as our own 401/404
                status = e.status_code if e.status_code in (400, 409, 422) else 502 if e.status_code < 500 else e.status_code
                body = {"error": e.code, "message": e.message, "upstream": "reclaim"}
            except KeyError:
                status, body = 404, {"error": "NOT_FOUND"}
            except Exception as e:  # never leak internals
                log(level="error", request_id=self._rid, error=type(e).__name__, msg=str(e)[:200])
                status, body = 500, {"error": "INTERNAL"}
            if isinstance(body, tuple):
                self._send(status, body[0], body[1], body[2] if len(body) > 2 else None)
            else:
                self._send(status, body)
            if self.path.startswith("/api/"):
                log(request_id=self._rid, method=method, path=urlparse(self.path).path, status=status, ms=round((time.monotonic() - t0) * 1000, 1),
                    user=USERS.get(self._token(), {}).get("id"))

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return H


def make_server(app: App, host="127.0.0.1", port=0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(app))


def main():
    port = int(os.environ.get("PORT", "8360"))
    host = os.environ.get("HOST", "127.0.0.1")
    app = App()
    srv = ThreadingHTTPServer((host, port), make_handler(app))
    log(event="startup", url=f"http://{host}:{port}", source=app.source.name, integrations=integration_status()["summary"])
    print(f"PayProof Decision Room: http://{host}:{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
