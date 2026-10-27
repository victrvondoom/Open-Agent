"""Source-system adapters.

`LocalFixtureSource` reads synthetic snapshots from data/cases (the default; SAMPLE_MODE).
`ZetarisSource` reads the same records through Zetaris's documented direct REST SQL route
(zetaris/getting-started, scripts/zetaris_sql.py RestChannel):

    POST {ZETARIS_REST_URL}/sql-editor/sqls/run          # REST URL ends in /api/v1.0
    Authorization: Bearer {ZETARIS_API_KEY}; X-Org-ID: {ZETARIS_ORG_ID}; X-Request-ID: uuid4
    {"queryId": uuid4, "sql": ..., "source": "SqlEditor", "limit": N}  ->  {"data": [[...], ...]}

It is enabled only when ZETARIS_REST_URL is set. Whether it has worked is reported at
runtime by `zetaris_status()`; it has not been run against a live Zetaris in this repo.

Either adapter returns the same shape: {case_id, dispute, feeds, sources{system: {system, records}}}.
Late-arriving events (stale-evidence simulation) are layered on top without
mutating the original records.
"""

import copy
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "data" / "cases"
USER_CASES_DIR = ROOT / "var" / "cases"  # disputes filed at runtime through intake
PLANS_PATH = ROOT / "data" / "plans.json"


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha(obj) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def load_plans():
    return json.loads(PLANS_PATH.read_text())


class LocalFixtureSource:
    name = "local-fixtures"
    live = False

    def __init__(self, cases_dir: Path = CASES_DIR, user_dir: Path | None = USER_CASES_DIR):
        self.cases_dir, self.user_dir = cases_dir, user_dir
        self._overlays: dict[str, list[dict]] = {}

    def _dirs(self):
        return [d for d in (self.cases_dir, self.user_dir) if d is not None]

    def list_case_ids(self):
        return sorted({p.stem for d in self._dirs() if d.exists() for p in d.glob("CASE-*.json")})

    def is_user_case(self, case_id: str) -> bool:
        return self.user_dir is not None and (self.user_dir / f"{case_id}.json").exists()

    def _base(self, case_id: str) -> dict:
        if not re.fullmatch(r"CASE-\d{4}", case_id or ""):
            raise KeyError(case_id)
        for d in self._dirs():
            path = d / f"{case_id}.json"
            if path.exists():
                return json.loads(path.read_text())
        raise KeyError(case_id)

    def load_case(self, case_id: str) -> dict:
        case = self._base(case_id)
        for event in self._overlays.get(case_id, []):
            system = event["system"]
            case["sources"][system]["records"].append(copy.deepcopy(event["record"]))
        case["late_events"] = copy.deepcopy(self._overlays.get(case_id, []))
        return case

    def inject_late_event(self, case_id: str, system: str, record: dict):
        self._base(case_id)  # existence check
        self._overlays.setdefault(case_id, []).append({"system": system, "record": record})

    def reset(self):
        self._overlays.clear()


# Fixed SQL templates. The direct REST route accepts SQL text (no bind parameters are
# documented), so the only interpolated values are validated against strict patterns:
# the database name ([A-Za-z_][A-Za-z0-9_]*) and the case key (CASE-\d{4}). Nothing a
# user or a model writes ever reaches the SQL text.
SYSTEMS = ("hris", "crm", "clm", "billing", "comp", "payroll")
SQL_TEMPLATE = ("SELECT record_id, record_type, payload_json FROM {db}.{system}_records "
                "WHERE case_key = '{case_key}' ORDER BY record_id")
CASE_KEY_RE = re.compile(r"CASE-\d{4}")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_ZETARIS_STATUS = {"last_ok_at": None, "last_error": None, "systems_served": [], "rows": 0, "url_host": None}


def zetaris_status():
    return dict(_ZETARIS_STATUS)


class ZetarisError(RuntimeError):
    pass


def build_sql(db: str, system: str, case_key: str) -> str:
    if system not in SYSTEMS:
        raise ZetarisError(f"system {system!r} not allowlisted")
    if not IDENT_RE.fullmatch(db):
        raise ZetarisError("ZETARIS_DATABASE must be a plain identifier")
    if not CASE_KEY_RE.fullmatch(case_key):
        raise ZetarisError("invalid case key")
    return SQL_TEMPLATE.format(db=db, system=system, case_key=case_key)


def map_rows(system: str, rows) -> list[dict]:
    """Map Zetaris rows back into the source-record model, preserving record ids."""
    out = []
    for row in rows or []:
        if isinstance(row, dict):
            rid, rtype, payload = row.get("record_id"), row.get("record_type"), row.get("payload_json")
        elif isinstance(row, (list, tuple)) and len(row) == 3:
            rid, rtype, payload = row
        else:
            raise ZetarisError(f"{system}: unexpected row shape")
        rec = json.loads(payload) if isinstance(payload, str) else payload
        if not isinstance(rec, dict) or rec.get("id") != rid or rec.get("type") != rtype:
            raise ZetarisError(f"{system}: row {rid!r} payload does not match its record_id/record_type")
        out.append(rec)
    return out


class ZetarisSource(LocalFixtureSource):
    """Per-system federated read through Zetaris with honest per-system provenance.
    A system whose query fails or times out falls back to the local fixture and is labelled
    `fixture-fallback (<reason>)`. A query that succeeds with zero rows is a real answer
    (e.g. no policy exceptions) and is labelled `zetaris (0 rows)`."""

    name = "zetaris"

    def __init__(self, rest_url: str, api_key: str, org_id: str, database: str = "payproof", timeout_s: float = 15):
        super().__init__()
        if not re.fullmatch(r"https?://[^\s]+", rest_url):
            raise ZetarisError("ZETARIS_REST_URL must be an http(s) URL ending in /api/v1.0")
        if not org_id or not org_id.isdigit():
            raise ZetarisError("ZETARIS_ORG_ID must be the numeric organisation ID")
        if not api_key:
            raise ZetarisError("ZETARIS_API_KEY is required")
        self.rest_url, self.org_id, self.database, self.timeout_s = rest_url.rstrip("/"), org_id, database, timeout_s
        self._key = api_key
        self.live = True
        _ZETARIS_STATUS["url_host"] = urllib.parse.urlparse(self.rest_url).netloc

    def run_sql(self, sql: str, limit: int = 500):
        body = json.dumps({"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": limit}).encode()
        req = urllib.request.Request(self.rest_url + "/sql-editor/sqls/run", data=body, method="POST", headers={
            "Authorization": f"Bearer {self._key}", "X-Org-ID": self.org_id, "X-Request-ID": str(uuid.uuid4()),
            "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                out = json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as e:
            e.close()
            raise ZetarisError(f"HTTP {e.code}") from e  # body not echoed: may contain request details
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise ZetarisError(f"unreachable ({type(e).__name__})") from e
        if not isinstance(out, dict) or not isinstance(out.get("data"), list):
            raise ZetarisError("response has no data array")
        return out["data"]

    def load_case(self, case_id: str) -> dict:
        case = super().load_case(case_id)
        provenance, served = {}, []
        for system in SYSTEMS:
            try:
                rows = self.run_sql(build_sql(self.database, system, case_id))
                records = map_rows(system, rows)
                # late-event overlay is local simulation state; keep it on top of Zetaris rows
                overlay = [e["record"] for e in case.get("late_events", []) if e["system"] == system]
                case["sources"][system]["records"] = records + overlay
                provenance[system] = "zetaris" if records else "zetaris (0 rows)"
                served.append(system)
                _ZETARIS_STATUS["rows"] += len(records)
            except (ZetarisError, json.JSONDecodeError) as exc:
                provenance[system] = f"fixture-fallback ({exc})"
                _ZETARIS_STATUS["last_error"] = f"{system}: {exc}"
        if served:
            _ZETARIS_STATUS["last_ok_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _ZETARIS_STATUS["systems_served"] = served
        case["provenance"] = provenance
        return case


def make_source():
    url = os.environ.get("ZETARIS_REST_URL")
    sample = os.environ.get("SAMPLE_MODE", "").lower() in ("1", "true", "yes")
    if url and not sample:
        return ZetarisSource(url, os.environ.get("ZETARIS_API_KEY", ""), os.environ.get("ZETARIS_ORG_ID", ""),
                             os.environ.get("ZETARIS_DATABASE", "payproof"), float(os.environ.get("ZETARIS_TIMEOUT_S", "15")))
    return LocalFixtureSource()
