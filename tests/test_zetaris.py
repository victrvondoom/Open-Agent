"""Zetaris adapter tests.

ContractTests run against a local stub that checks the documented direct-REST request
shape; they prove the adapter's mapping, validation and fallback logic, NOT a live
Zetaris. LiveSmokeTest runs only when ZETARIS_REST_URL/ZETARIS_API_KEY/ZETARIS_ORG_ID
are set and the fixtures are registered (docs/zetaris/register.sql).
"""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from payproof import sources
from payproof.sources import LocalFixtureSource, ZetarisError, ZetarisSource, build_sql, map_rows

FIXTURES = LocalFixtureSource()


class Stub(BaseHTTPRequestHandler):
    mode = "ok"
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "org": self.headers.get("X-Org-ID"),
                          "rid": self.headers.get("X-Request-ID"), "body": body})
        if Stub.mode == "401":
            self.send_response(401); self.end_headers(); return
        system = body["sql"].split("payproof.")[1].split("_records")[0]
        case_key = body["sql"].split("case_key = '")[1].split("'")[0]
        recs = FIXTURES.load_case(case_key)["sources"][system]["records"]
        rows = [] if (Stub.mode == "empty" or (Stub.mode == "partial" and system == "payroll")) else \
            [[r["id"], r["type"], json.dumps(r)] for r in recs]
        out = json.dumps({"data": rows}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/api/v1.0"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        Stub.mode, Stub.seen = "ok", []
        self.status_before = dict(sources._ZETARIS_STATUS)

    def tearDown(self):  # a stub must never leave the adapter looking live
        sources._ZETARIS_STATUS.clear(); sources._ZETARIS_STATUS.update(self.status_before)

    def src(self):
        return ZetarisSource(self.url, "test-key", "42", timeout_s=5)

    def test_documented_request_shape_and_faithful_mapping(self):
        case = self.src().load_case("CASE-1001")
        req = Stub.seen[0]
        self.assertEqual(req["path"], "/api/v1.0/sql-editor/sqls/run")
        self.assertEqual(req["auth"], "Bearer test-key")
        self.assertEqual(req["org"], "42")
        self.assertTrue(req["rid"])
        self.assertEqual(set(req["body"]), {"queryId", "sql", "source", "limit"})
        self.assertEqual(req["body"]["source"], "SqlEditor")
        self.assertEqual(case["provenance"]["comp"], "zetaris (0 rows)")  # CASE-1001 has no exceptions
        self.assertTrue(all(v.startswith("zetaris") for v in case["provenance"].values()))
        self.assertEqual(case["sources"], FIXTURES.load_case("CASE-1001")["sources"])

    def test_empty_result_is_served_not_backfilled(self):
        Stub.mode = "partial"
        case = self.src().load_case("CASE-1001")
        self.assertEqual(case["provenance"]["crm"], "zetaris")
        self.assertEqual(case["provenance"]["payroll"], "zetaris (0 rows)")
        self.assertEqual(case["sources"]["payroll"]["records"], [])

    def test_auth_error_falls_back_without_leaking_body(self):
        Stub.mode = "401"
        case = self.src().load_case("CASE-1001")
        self.assertTrue(all(v == "fixture-fallback (HTTP 401)" for v in case["provenance"].values()))

    def test_unreachable_falls_back(self):
        case = ZetarisSource("http://127.0.0.1:1/api/v1.0", "k", "42", timeout_s=1).load_case("CASE-1001")
        self.assertTrue(all(v.startswith("fixture-fallback (unreachable") for v in case["provenance"].values()))

    def test_validation(self):
        with self.assertRaises(ZetarisError):
            build_sql("payproof", "crm", "CASE-1001' OR '1'='1")
        with self.assertRaises(ZetarisError):
            ZetarisSource(self.url, "k", "not-numeric")
        with self.assertRaises(ZetarisError):
            map_rows("crm", [["OPP-1", "opportunity", json.dumps({"id": "OPP-2", "type": "opportunity"})]])

    def test_investigation_through_zetaris_matches_fixtures(self):
        from payproof.sources import load_plans
        from payproof.workflow import investigate
        a = investigate(self.src().load_case("CASE-1001"), load_plans())
        b = investigate(FIXTURES.load_case("CASE-1001"), load_plans())
        self.assertEqual(a["calculation"]["due"], b["calculation"]["due"])
        self.assertEqual(a["sources_meta"]["provenance"]["billing"], "zetaris")


@unittest.skipUnless(os.environ.get("ZETARIS_REST_URL") and os.environ.get("ZETARIS_API_KEY") and os.environ.get("ZETARIS_ORG_ID"),
                     "live Zetaris credentials not configured")
class LiveSmokeTest(unittest.TestCase):
    def test_live_zetaris_serves_demo_case(self):
        src = sources.make_source()
        case = src.load_case("CASE-1001")
        self.assertEqual(case["provenance"]["billing"], "zetaris", case["provenance"])
        self.assertEqual(case["sources"]["billing"], FIXTURES.load_case("CASE-1001")["sources"]["billing"])


if __name__ == "__main__":
    unittest.main()
