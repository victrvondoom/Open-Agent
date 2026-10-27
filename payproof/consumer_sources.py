"""Consumer-dispute sources: claim files + institution records federated per system.

Institution systems (airline_pss, flight_ops, payments, airport_ops) are queried through the
Zetaris REST adapter when ZETARIS_REST_URL is configured, otherwise read from declared local
fixture tables (data/consumer/lake/). Provenance is per system and honest:
    zetaris | zetaris (0 rows) | fixture-fallback (<reason>) | unavailable (<reason>) | local-fixtures
Every query yields a lineage entry (query id, selector/SQL, mode, rows, latency, retrieval time).

SQL safety: the REST route takes SQL text with no documented bind parameters, so the only
interpolated values are validated against strict allowlists (booking ref [A-Z0-9]{6}, IATA [A-Z]{3},
system names from SYSTEMS, database identifier). Nothing a claimant or a model writes reaches SQL.
"""

import json
import os
import re
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .sources import IDENT_RE, ZetarisError, ZetarisSource, _ZETARIS_STATUS, map_rows, sha

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "data" / "consumer" / "cases"
LAKE_DIR = ROOT / "data" / "consumer" / "lake"
VAR_DIR = ROOT / "var" / "consumer"
SYSTEMS = ("airline_pss", "flight_ops", "payments", "airport_ops")
SYSTEM_LABEL = {"airline_pss": "carrier passenger service system", "flight_ops": "carrier flight operations",
                "payments": "card network / issuer statement", "airport_ops": "airport operations notices"}
CASE_ID_RE = re.compile(r"CDX-\d{4}")
REF_RE = re.compile(r"[A-Z0-9]{6}")
IATA_RE = re.compile(r"[A-Z]{3}")
SQL_BY_REF = ("SELECT record_id, record_type, payload_json FROM {db}.consumer_{system} "
              "WHERE booking_ref = '{ref}' ORDER BY record_id")
SQL_BY_AIRPORT = ("SELECT record_id, record_type, payload_json FROM {db}.consumer_airport_ops "
                  "WHERE airport IN ({airports}) ORDER BY record_id")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_consumer_sql(db: str, system: str, ref: str | None = None, airports: tuple = ()) -> str:
    if system not in SYSTEMS:
        raise ZetarisError(f"system {system!r} not allowlisted")
    if not IDENT_RE.fullmatch(db):
        raise ZetarisError("ZETARIS_DATABASE must be a plain identifier")
    if system == "airport_ops":
        if not airports or not all(IATA_RE.fullmatch(a or "") for a in airports):
            raise ZetarisError("invalid airport code")
        return SQL_BY_AIRPORT.format(db=db, airports=", ".join(f"'{a}'" for a in sorted(set(airports))))
    if not REF_RE.fullmatch(ref or ""):
        raise ZetarisError("invalid booking reference")
    return SQL_BY_REF.format(db=db, system=system, ref=ref)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


class ConsumerSource:
    """lake: fixture tables {system: [records]}; case_records: optional per-case record sets used by the
    benchmark so generated cases never see each other's records (a case-scoped federated view)."""

    def __init__(self, lake: dict | None = None, cases: dict | None = None, case_records: dict | None = None,
                 zetaris: ZetarisSource | None = None, var_dir: Path | None = VAR_DIR, cases_dir: Path = CASES_DIR):
        self.lake = lake if lake is not None else {s: _read_json(LAKE_DIR / f"{s}.json", []) for s in SYSTEMS}
        self.lake_feeds = _read_json(LAKE_DIR / "_feeds.json", {}) if lake is None else {}
        self._cases = cases
        self.case_records = case_records or {}
        self.zetaris = zetaris
        self.var_dir, self.cases_dir = var_dir, cases_dir
        self.overlays: dict[str, list] = {}
        self.lock = threading.RLock()
        self.name = "zetaris" if zetaris else "local-fixtures"
        overlay_dir = var_dir / "overlays" if var_dir else None
        if overlay_dir and overlay_dir.exists():
            for f in overlay_dir.glob("CDX-*.json"):
                self.overlays[f.stem] = _read_json(f, [])

    # ------------------------------------------------------------------ claims
    def _claim_files(self) -> dict:
        if self._cases is not None:
            return self._cases
        out = {}
        for d in (self.cases_dir, (self.var_dir / "cases") if self.var_dir else None):
            if d and d.exists():
                for f in sorted(d.glob("CDX-*.json")):
                    out[f.stem] = f
        return out

    def list_case_ids(self) -> list[str]:
        return sorted(self._claim_files())

    def load_claim(self, case_id: str) -> dict:
        if not CASE_ID_RE.fullmatch(case_id or ""):
            raise KeyError(case_id)
        src = self._claim_files()[case_id]
        return deepcopy(src) if isinstance(src, dict) else json.loads(src.read_text(encoding="utf-8"))

    def create_case(self, claim_case: dict) -> dict:
        """Persist a newly filed claim (intake). Ids are allocated under a lock."""
        with self.lock:
            n = max([int(c[4:]) for c in self.list_case_ids() if int(c[4:]) >= 4001] + [4000]) + 1
            case = {**claim_case, "case_id": f"CDX-{n:04d}"}
            case["dispute"] = {**case["dispute"], "id": f"CLM-{n}"}
            self._write_claim(case)
            return case

    def save_claim(self, case: dict):
        """Persist claim-level updates (e.g. the RECLAIM link). Shipped fixtures are never rewritten."""
        with self.lock:
            src = self._claim_files().get(case["case_id"])
            if isinstance(src, Path) and not str(src.resolve()).startswith(str(self.var_dir.resolve() if self.var_dir else "")):
                d = self.var_dir / "cases"  # a shipped fixture gets a runtime copy that shadows it
                d.mkdir(parents=True, exist_ok=True)
            self._write_claim(case)

    def _write_claim(self, case: dict):
        claim = {k: v for k, v in case.items() if k not in ("sources", "feeds", "provenance", "queries", "late_events")}
        if self._cases is not None:
            self._cases[case["case_id"]] = claim
            return
        d = self.var_dir / "cases"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{case['case_id']}.json").write_text(json.dumps(claim, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ federation
    def _fixture_rows(self, case_id, system, ref, airports):
        table = self.case_records[case_id].get(system, []) if case_id in self.case_records else self.lake.get(system, [])
        if system == "airport_ops":
            return [r for r in table if r.get("airport") in airports]
        return [r for r in table if r.get("booking_ref") == ref]

    def federate(self, case_id: str, system: str, ref: str, airports: tuple = ()) -> tuple[list, dict]:
        t0 = time.monotonic()
        selector = f"airport IN {sorted(set(airports))}" if system == "airport_ops" else f"booking_ref = {ref}"
        meta = {"system": system, "selector": selector, "retrieved_at": now_iso()}
        if self.zetaris:
            try:
                sql = build_consumer_sql(self.zetaris.database, system, ref, airports)
                rows = map_rows(system, self.zetaris.run_sql(sql))
                meta.update(query_id=f"ZQ-{uuid.uuid4().hex[:12]}", mode="zetaris", sql=sql, rows=len(rows),
                            ms=round((time.monotonic() - t0) * 1000, 1), provenance="zetaris" if rows else "zetaris (0 rows)")
                _ZETARIS_STATUS["rows"] += len(rows)
                _ZETARIS_STATUS["last_ok_at"] = now_iso()
                return rows, meta
            except (ZetarisError, json.JSONDecodeError) as exc:
                _ZETARIS_STATUS["last_error"] = f"consumer_{system}: {exc}"
                if not (case_id in self.case_records or self.lake.get(system)):
                    meta.update(query_id=f"ZQ-{uuid.uuid4().hex[:12]}", mode="zetaris", rows=0, ms=round((time.monotonic() - t0) * 1000, 1),
                                provenance=f"unavailable ({exc})", unavailable=True)
                    return [], meta
                rows = self._fixture_rows(case_id, system, ref, airports)
                meta.update(query_id="FQ-" + sha([case_id, system, selector])[:12], mode="fixture", rows=len(rows),
                            ms=round((time.monotonic() - t0) * 1000, 1), provenance=f"fixture-fallback ({exc})", degraded=True)
                return deepcopy(rows), meta
        rows = self._fixture_rows(case_id, system, ref, airports)
        meta.update(query_id="FQ-" + sha([case_id, system, selector])[:12], mode="fixture", rows=len(rows),
                    ms=round((time.monotonic() - t0) * 1000, 1), provenance="local-fixtures")
        return deepcopy(rows), meta

    def load_case(self, case_id: str) -> dict:
        case = self.load_claim(case_id)
        if case.get("as_of_mode") == "live":  # runtime-filed claims: live clock, or the declared fixture clock
            case["as_of"] = now_iso() if self.zetaris else self.lake_feeds.get("_clock", now_iso())
        ref = case["dispute"].get("booking_ref", "")
        sources, provenance, queries = {}, {}, []
        for system in ("airline_pss", "flight_ops", "payments"):
            rows, meta = self.federate(case_id, system, ref)
            sources[system], provenance[system] = rows, meta["provenance"]
            queries.append(meta)
        airports = tuple(sorted({a for b in sources["airline_pss"] if b.get("type") == "booking"
                                 for a in (b.get("origin"), b.get("destination")) if a}))
        if airports:
            rows, meta = self.federate(case_id, "airport_ops", ref, airports)
        else:
            rows, meta = [], {"system": "airport_ops", "selector": "skipped: no booking airports", "rows": 0, "mode": "none",
                              "provenance": "not queried", "query_id": None, "retrieved_at": now_iso()}
        sources["airport_ops"], provenance["airport_ops"] = rows, meta["provenance"]
        queries.append(meta)
        overrides = case.pop("feed_overrides", {}) or {}
        feeds = {}
        for system in SYSTEMS:
            q = next(m for m in queries if m["system"] == system)
            live = q.get("mode") == "zetaris" and not q.get("unavailable")
            base = {"as_of": now_iso() if live else self.lake_feeds.get(system, {}).get("as_of", case.get("as_of")),
                    "status": "unavailable" if q.get("unavailable") else "ok", **({"live": True} if live else {})}
            if q.get("unavailable"):
                base["reason"] = q["provenance"]
            feeds[system] = {**base, **overrides.get(system, {})}
            if feeds[system]["status"] == "unavailable":
                sources[system] = []
        for ev in self.overlays.get(case_id, []):  # simulated late-arriving records stay on top of any source
            sources.setdefault(ev["system"], []).append(ev["record"])
        case["sources"] = {s: {"system": SYSTEM_LABEL[s], "records": sorted(sources[s], key=lambda r: r["id"])} for s in SYSTEMS}
        case["feeds"], case["provenance"], case["queries"] = feeds, provenance, queries
        case["late_events"] = list(self.overlays.get(case_id, []))
        return case

    def requery(self, case: dict, record_id: str) -> tuple[dict | None, dict]:
        """Independent re-read of one record through the same adapter (the skeptic's path)."""
        system = next((s for s, blk in case["sources"].items() if any(r["id"] == record_id for r in blk["records"])), None)
        if not system:
            return None, {"record_id": record_id, "error": "not in case"}
        airports = tuple(sorted({a for b in case["sources"]["airline_pss"]["records"] if b.get("type") == "booking"
                                 for a in (b.get("origin"), b.get("destination")) if a}))
        rows, meta = self.federate(case["case_id"], system, case["dispute"].get("booking_ref", ""), airports)
        rows += [deepcopy(e["record"]) for e in self.overlays.get(case["case_id"], []) if e["system"] == system]
        return next((r for r in rows if r["id"] == record_id), None), {**meta, "record_id": record_id}

    # ------------------------------------------------------------------ simulation
    def inject_late_event(self, case_id: str, system: str, record: dict):
        if system not in SYSTEMS:
            raise ValueError("unknown system")
        with self.lock:
            self.overlays.setdefault(case_id, []).append({"system": system, "record": record, "injected_at": now_iso()})
            if self.var_dir:
                d = self.var_dir / "overlays"
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{case_id}.json").write_text(json.dumps(self.overlays[case_id], indent=2), encoding="utf-8")

    def reset(self):
        with self.lock:
            self.overlays.clear()
            if self.var_dir and (self.var_dir / "overlays").exists():
                for f in (self.var_dir / "overlays").glob("*.json"):
                    f.unlink(missing_ok=True)


def unfiled_bookings() -> list[dict]:
    """Bookings present in the fixture lake that nobody has disputed yet (offered to the intake form)."""
    return _read_json(LAKE_DIR / "_unfiled_bookings.json", [])


def make_consumer_source(var_dir: Path | None = VAR_DIR) -> ConsumerSource:
    url = os.environ.get("ZETARIS_REST_URL")
    sample = os.environ.get("SAMPLE_MODE", "").lower() in ("1", "true", "yes")
    if url and not sample:
        z = ZetarisSource(url, os.environ.get("ZETARIS_API_KEY", ""), os.environ.get("ZETARIS_ORG_ID", ""),
                          os.environ.get("ZETARIS_DATABASE", "payproof"), float(os.environ.get("ZETARIS_TIMEOUT_S", "15")))
        return ConsumerSource(zetaris=z, var_dir=var_dir)
    return ConsumerSource(var_dir=var_dir)
