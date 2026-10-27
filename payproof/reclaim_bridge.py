"""HTTP bridge from PayProof to RECLAIM's FastAPI backend (RECLAIM keeps intake, documents, agents).

Endpoints used (verified against RECLAIM's live /openapi.json and source, 2026-10-27):
    GET  /health                                  service health (server root, not /api/v1)
    POST /api/v1/cases                            CaseCreate {title, institution_name, summary, domain, jurisdiction} -> CaseRead
    GET  /api/v1/cases[?domain=] , /cases/{id}    CaseRead (owner-scoped: 404 for another principal's case)
    POST /api/v1/agents/run-case                  {case_id, include_negotiation_draft} -> AgentRunResponse
    POST /api/v1/upload/{case_id}/documents       multipart `file` (PDF or image, <= 10 MB)
    GET  /api/v1/upload/{case_id}/documents       document rows incl. text_extract
    POST /api/v1/cases/{case_id}/events           {event_type, title, body}
    GET  /api/v1/timeline/{case_id}               case events

Tenancy: RECLAIM scopes cases to the authenticated principal. Each PayProof tenant gets its own
principal (RECLAIM_TOKEN_<TENANT> if set, else the dev-mode principal "payproof-<tenant>"), so one
tenant's RECLAIM cases are invisible to another. Non-idempotent POSTs are never retried
automatically. Status is LIVE only after a real successful call in this process.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

DEFAULT_RECLAIM_URL = "http://127.0.0.1:8001/api/v1"
DEFAULT_TIMEOUT_S = 60.0
GET_RETRIES = 2
DOMAINS = {"health_insurance", "banking", "telecom", "airlines", "housing", "ecommerce", "government", "healthcare"}
AGENT_REQUIRED = ("case_id", "status", "evidence_summary", "research_summary", "strategy", "appeal_draft", "review_notes", "citations")
AGENT_OPTIONAL = ("route", "agent_trace", "specialist_outputs", "llm_call_count", "workflow_engine", "final_answer")
CASE_REQUIRED = ("id", "user_id", "domain", "title", "institution_name", "summary", "jurisdiction", "status")

_LOCK = threading.Lock()
_STATUS = {"last_ok_at": None, "last_error": None, "last_error_code": None, "last_latency_ms": None,
           "calls_ok": 0, "calls_failed": 0, "last_endpoint": None, "service": None}


class ReclaimBridgeError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.status_code, self.details = code, message, status_code, details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "status_code": self.status_code, "details": self.details}}


def get_bridge_config() -> dict:
    url = os.environ.get("RECLAIM_API_URL", DEFAULT_RECLAIM_URL).rstrip("/")
    return {"url": url, "root": re.sub(r"/api/v\d+$", "", url),
            "sample_mode": os.environ.get("SAMPLE_MODE", "").lower() in ("1", "true", "yes"),
            "disabled": os.environ.get("RECLAIM_DISABLED", "").lower() in ("1", "true", "yes"),
            "timeout": float(os.environ.get("RECLAIM_TIMEOUT_S", DEFAULT_TIMEOUT_S))}


def principal_for(tenant: str) -> str:
    """Bearer credential for a PayProof tenant. A configured token wins; otherwise a stable dev-mode principal."""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", tenant or ""):
        raise ReclaimBridgeError("BAD_TENANT", "tenant id is not a valid identifier", 400)
    return os.environ.get(f"RECLAIM_TOKEN_{tenant.upper().replace('-', '_')}") or f"payproof-{tenant}"


def bridge_status() -> dict:
    cfg = get_bridge_config()
    with _LOCK:
        s = dict(_STATUS)
    configured = not (cfg["sample_mode"] or cfg["disabled"])
    state = ("FALLBACK" if not configured else "LIVE" if s["last_ok_at"] and not s["last_error"] else
             "DEGRADED" if s["last_ok_at"] else "UNAVAILABLE" if s["last_error"] else "CONFIGURED_UNVERIFIED")
    detail = {"LIVE": f"RECLAIM @ {cfg['url']} - {s['calls_ok']} successful call(s); last {s['last_endpoint']}",
              "DEGRADED": f"RECLAIM @ {cfg['url']} answered earlier but the last call failed ({s['last_error']})",
              "UNAVAILABLE": f"RECLAIM @ {cfg['url']} unreachable: {s['last_error']}",
              "CONFIGURED_UNVERIFIED": f"RECLAIM configured @ {cfg['url']}; no call made yet in this process",
              "FALLBACK": "RECLAIM disabled (SAMPLE_MODE / RECLAIM_DISABLED): consumer cases use local fixtures only"}[state]
    return {"sponsor": "RECLAIM Multi-Agent", "key": "reclaim", "state": state, "configured": configured, "endpoint": cfg["url"],
            "last_success": s["last_ok_at"], "last_error": s["last_error"], "last_error_code": s["last_error_code"],
            "latency_ms": s["last_latency_ms"], "calls_ok": s["calls_ok"], "calls_failed": s["calls_failed"],
            "service": s["service"], "detail": detail}


def _record(ok: bool, endpoint: str, ms: float, error: str | None = None, code=None):
    with _LOCK:
        _STATUS.update(last_latency_ms=round(ms, 1), last_endpoint=endpoint)
        if ok:
            _STATUS["calls_ok"] += 1
            _STATUS.update(last_ok_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), last_error=None, last_error_code=None)
        else:
            _STATUS["calls_failed"] += 1
            _STATUS.update(last_error=error, last_error_code=code)


def text_pdf(text: str, title: str = "") -> bytes:
    """Minimal single-page PDF (Helvetica, WinAnsi) so text documents can enter RECLAIM's vault,
    which accepts PDF or images only. Non-Latin-1 characters are transliterated, never dropped silently."""
    def esc(s):
        s = s.replace("₹", "INR ").encode("latin-1", "replace").decode("latin-1")
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    lines = []
    for raw in ([title, ""] if title else []) + str(text).splitlines():
        while len(raw) > 95:
            cut = raw.rfind(" ", 0, 95)
            cut = cut if cut > 40 else 95
            lines.append(raw[:cut])
            raw = raw[cut:].lstrip()
        lines.append(raw)
    stream = ("BT /F1 10 Tf 50 800 Td 14 TL " + " ".join(f"({esc(line)}) Tj T*" for line in lines[:52]) + " ET").encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


class ReclaimBridgeClient:
    def __init__(self, config: dict | None = None):
        self.cfg = config or get_bridge_config()

    def _request(self, method: str, path: str, tenant: str | None, body: dict | None = None, raw: bytes | None = None,
                 content_type: str = "application/json", root: bool = False) -> Any:
        if self.cfg["sample_mode"] or self.cfg["disabled"]:
            raise ReclaimBridgeError("RECLAIM_DISABLED", "RECLAIM bridge disabled (SAMPLE_MODE or RECLAIM_DISABLED)", 503)
        url = f"{self.cfg['root'] if root else self.cfg['url']}/{path.lstrip('/')}"
        headers = {"Accept": "application/json", "User-Agent": "PayProof-RECLAIM-Bridge/2.0", "X-Request-ID": uuid.uuid4().hex[:16]}
        if tenant:
            headers["Authorization"] = f"Bearer {principal_for(tenant)}"
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        if data is not None:
            headers["Content-Type"] = content_type
        attempts = 1 + (GET_RETRIES if method == "GET" else 0)  # never auto-retry a non-idempotent write
        endpoint = f"{method} {'/' if root else '/api/v1/'}{path.lstrip('/').split('?')[0]}"
        last = None
        for attempt in range(attempts):
            t0 = time.monotonic()
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=self.cfg["timeout"]) as resp:
                    payload = resp.read().decode("utf-8")
                _record(True, endpoint, (time.monotonic() - t0) * 1000)
                try:
                    return json.loads(payload) if payload else None
                except json.JSONDecodeError as exc:
                    raise ReclaimBridgeError("INVALID_JSON", f"RECLAIM returned malformed JSON for {endpoint}", 502) from exc
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                exc.close()
                _record(False, endpoint, (time.monotonic() - t0) * 1000, f"HTTP {exc.code}", exc.code)
                if exc.code < 500:
                    raise ReclaimBridgeError(f"RECLAIM_HTTP_{exc.code}", f"RECLAIM {endpoint} returned HTTP {exc.code}", exc.code,
                                             {"body": detail}) from exc
                last = exc
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                _record(False, endpoint, (time.monotonic() - t0) * 1000, type(exc).__name__, "unreachable")
                last = exc
            if attempt + 1 < attempts:
                time.sleep(0.25 * (2 ** attempt))
        raise ReclaimBridgeError("RECLAIM_UNREACHABLE", f"RECLAIM {endpoint} failed after {attempts} attempt(s): {type(last).__name__}",
                                 503)

    @staticmethod
    def _require(obj, fields, what):
        if not isinstance(obj, dict):
            raise ReclaimBridgeError("CONTRACT_VIOLATION", f"{what}: expected an object", 502)
        missing = [f for f in fields if f not in obj]
        if missing:
            raise ReclaimBridgeError("CONTRACT_VIOLATION", f"{what}: missing required field(s) {missing}", 502)
        return obj

    # ------------------------------------------------------------------ endpoints
    def health(self) -> dict:
        h = self._request("GET", "health", None, root=True)
        with _LOCK:
            _STATUS["service"] = {k: (h or {}).get(k) for k in ("status", "service", "environment", "llm")}
        return h

    def ping(self, tenant: str = "north") -> dict:
        try:
            h = self.health()
            cases = self.list_cases(tenant)
            return {"ok": True, "endpoint": self.cfg["url"], "health": (h or {}).get("status"), "environment": (h or {}).get("environment"),
                    "cases_visible_to_tenant": len(cases)}
        except ReclaimBridgeError as exc:
            return {"ok": False, "endpoint": self.cfg["url"], "error": exc.code, "message": exc.message}

    def create_case(self, tenant: str, title: str, institution_name: str, summary: str, domain: str = "airlines",
                    jurisdiction: str = "IN") -> dict:
        if domain not in DOMAINS:
            raise ReclaimBridgeError("BAD_DOMAIN", f"domain {domain!r} not accepted by RECLAIM", 400)
        body = {"title": title[:160].ljust(4, "."), "institution_name": institution_name[:160].ljust(2, "."),
                "summary": summary[:4000].ljust(10, "."), "domain": domain, "jurisdiction": jurisdiction[:80]}
        return self._require(self._request("POST", "cases", tenant, body), CASE_REQUIRED, "CaseRead")

    def get_case(self, tenant: str, case_id: str) -> dict:
        return self._require(self._request("GET", f"cases/{case_id}", tenant), CASE_REQUIRED, "CaseRead")

    def list_cases(self, tenant: str, domain: str | None = None) -> list:
        res = self._request("GET", "cases" + (f"?domain={domain}" if domain in DOMAINS else ""), tenant)
        if not isinstance(res, list):
            raise ReclaimBridgeError("CONTRACT_VIOLATION", "GET /cases: expected a list", 502)
        return res

    def run_agents(self, tenant: str, case_id: str, include_negotiation_draft: bool = True) -> dict:
        raw = self._require(self._request("POST", "agents/run-case", tenant,
                                          {"case_id": case_id, "include_negotiation_draft": include_negotiation_draft}),
                            AGENT_REQUIRED, "AgentRunResponse")
        if not isinstance(raw["citations"], list) or not isinstance(raw["review_notes"], list):
            raise ReclaimBridgeError("CONTRACT_VIOLATION", "AgentRunResponse: citations/review_notes must be lists", 502)
        return {**{k: raw[k] for k in AGENT_REQUIRED}, **{k: raw.get(k) for k in AGENT_OPTIONAL},
                "provenance": "reclaim-live", "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def upload_document(self, tenant: str, case_id: str, filename: str, content: bytes, mime: str = "application/pdf") -> dict:
        boundary = "payproof" + uuid.uuid4().hex
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:80] or "document.pdf"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{safe}\"\r\n"
                f"Content-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        res = self._request("POST", f"upload/{case_id}/documents", tenant, raw=body,
                            content_type=f"multipart/form-data; boundary={boundary}")
        return self._require(res, ("document_id", "case_id", "filename"), "DocumentUploadResponse")

    def list_documents(self, tenant: str, case_id: str) -> list:
        res = self._request("GET", f"upload/{case_id}/documents", tenant)
        if not isinstance(res, list):
            raise ReclaimBridgeError("CONTRACT_VIOLATION", "GET documents: expected a list", 502)
        return res

    def add_event(self, tenant: str, case_id: str, event_type: str, title: str, body: str = "") -> dict:
        return self._require(self._request("POST", f"cases/{case_id}/events", tenant,
                                           {"event_type": event_type[:80], "title": title[:160], "body": body[:4000]}),
                             ("id", "case_id", "event_type"), "CaseEvent")

    def timeline(self, tenant: str, case_id: str) -> list:
        res = self._request("GET", f"timeline/{case_id}", tenant)
        return res if isinstance(res, list) else []
