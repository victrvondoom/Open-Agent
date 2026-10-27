"""PayProof HTTP API + Decision Room static UI. Standard library only.

Run: python3 -m payproof.server   (PORT env var, default 8360)
"""

import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .actions import USERS, ActionError, ActionService, late_credit_note
from .integrations import integration_status
from .sources import make_source, load_plans

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}


class App:
    def __init__(self):
        self.source = make_source()
        self.plans = load_plans()
        self.svc = ActionService(self.source, self.plans)
        self.cache = {}

    def investigation(self, case_id):
        return self.svc.investigate(case_id)

    def queue(self, user):
        out = []
        for cid in self.source.list_case_ids():
            r = self.investigation(cid)
            if user and user["role"] == "sales_rep" and r["dispute"]["employee_id"] != user["id"]:
                continue
            acts = [a for a in self.svc.actions.values() if a["case_id"] == cid]
            emp = next(n for n in r["graph"]["nodes"] if n["id"] == r["dispute"]["employee_id"])
            exposure = abs(float(r["calculation"]["delta"])) if r["calculation"]["delta"] else float(r["dispute"]["claimed_shortfall"])
            out.append({"case_id": cid, "title": r["title"], "claimant": emp["label"], "employee_id": r["dispute"]["employee_id"],
                        "claimed": r["dispute"]["claimed_shortfall"], "delta": r["calculation"]["delta"],
                        "exposure": f"{exposure:.2f}", "proof_status": r["proof_status"], "verdict": r["verdict"],
                        "action": r["proposed_action"]["type"], "action_state": acts[-1]["state"] if acts else None,
                        "filed_at": r["dispute"]["filed_at"], "tags": r["tags"]})
        out.sort(key=lambda x: (0 if "demo" in x["tags"] else 1, -float(x["exposure"])))
        return out


def log(**kw):
    sys.stderr.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **kw}) + "\n")


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        server_version = "PayProof/1.0"

        def log_message(self, *a):
            pass

        def _send(self, status, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
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
            if method == "GET" and path == "/api/users":
                return 200, [{"token": t, **{k: v for k, v in u.items() if k != "perms"}, "perms": sorted(u["perms"])}
                             for t, u in USERS.items()]
            if method == "GET" and path == "/api/cases":
                return 200, app.queue(self._viewer())
            if (g := m(r"/api/cases/(CASE-\d{4})")) and method == "GET":
                self._check_case_access(self._viewer(), g[1])
                r = app.investigation(g[1])
                r["actions"] = [a for a in app.svc.actions.values() if a["case_id"] == g[1]]
                return 200, r
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
                return 200, {"reset": True}
            if method == "GET" and path == "/api/audit":
                self._viewer()
                return 200, {"chain_valid": app.svc.audit.verify_chain(), "entries": app.svc.audit.entries[-200:]}
            if method == "GET" and path == "/api/benchmark":
                p = ROOT / "bench" / "results" / "latest.json"
                return (200, json.loads(p.read_text())) if p.exists() else (404, {"error": "run python3 -m payproof.bench"})
            return 404, {"error": "not found"}

        def _static(self, path):
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            f = (WEB / rel).resolve()
            if not str(f).startswith(str(WEB.resolve())) or not f.is_file():
                return 404, {"error": "not found"}
            return 200, (f.read_bytes(), MIME.get(f.suffix, "application/octet-stream"))

        def _handle(self, method):
            t0 = time.monotonic()
            try:
                status, body = self._route(method)
            except ActionError as e:
                status, body = e.status, {"error": e.code, "message": e.message}
            except KeyError:
                status, body = 404, {"error": "NOT_FOUND"}
            except Exception as e:  # never leak internals
                log(level="error", error=type(e).__name__, msg=str(e)[:200])
                status, body = 500, {"error": "INTERNAL"}
            if isinstance(body, tuple):
                self._send(status, body[0], body[1])
            else:
                self._send(status, body)
            if self.path.startswith("/api/"):
                log(method=method, path=urlparse(self.path).path, status=status, ms=round((time.monotonic() - t0) * 1000, 1),
                    user=USERS.get(self._token(), {}).get("id"))

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return H


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
