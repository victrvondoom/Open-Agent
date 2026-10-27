"""Dispute intake: validation, round trip through the full pipeline, and API permissions."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from payproof.intake import IntakeError, create_case, spec_from_form, template_from_case
from payproof.sources import LocalFixtureSource, load_plans
from payproof.workflow import investigate

PLANS = load_plans()


def demo_form():
    return template_from_case(LocalFixtureSource(user_dir=None).load_case("CASE-1001"))


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.src = LocalFixtureSource(user_dir=self.dir)

    def file(self, form):
        case = create_case(form, set(self.src.list_case_ids()), directory=self.dir)
        return investigate(self.src.load_case(case["case_id"]), PLANS)

    def test_template_round_trip_reproduces_demo_outcome(self):
        r = self.file(demo_form())
        self.assertTrue(r["case_id"].startswith("CASE-2"))
        self.assertEqual((r["proof_status"], r["verdict"]), ("VERIFIED", "PARTIALLY_SUPPORTED"))
        self.assertEqual((r["calculation"]["due"], r["calculation"]["paid"], r["calculation"]["delta"]), ("4300.00", "3200.00", "1100.00"))
        self.assertTrue(any(f["id"].startswith("SK-DUP") for f in r["skeptic"]["findings"]))
        self.assertTrue(any(f["id"].startswith("SK-LATE") for f in r["skeptic"]["findings"]))

    def test_edits_change_the_outcome(self):
        form = demo_form()
        form["payroll"] = [{"amount": "4300.00", "posted_date": "2026-06-30", "type": "commission"}]
        r = self.file(form)
        self.assertEqual((r["verdict"], r["proposed_action"]["type"]), ("REJECTED", "RECONCILIATION_REPORT"))
        form = demo_form()
        form["contract_tcv"], form["amendment"] = "", None
        self.assertEqual(self.file(form)["proof_status"], "NEEDS_EVIDENCE")
        form = demo_form()
        form["crm_email"] = "someone.else@other.example"
        form["crm_name"] = form["rep_name"]
        r = self.file(form)
        self.assertEqual(r["identity"]["status"], "WEAK_ONLY")
        self.assertEqual(r["proof_status"], "NEEDS_EVIDENCE")

    def test_ordinary_punctuation_is_accepted(self):
        form = demo_form()
        form["title"] = "Acme Robotics — “edited” intake, Q2 (50%)"
        form["narrative"] = "I'm owed €1,000 – see invoice #42;\nthanks!"
        spec = spec_from_form(form, "CASE-2001")
        self.assertEqual(spec["title"], form["title"])
        self.assertEqual(spec["narrative"], "I'm owed €1,000 – see invoice #42; thanks!")

    def test_ids_are_unique_and_sequential(self):
        a = create_case(demo_form(), set(self.src.list_case_ids()), directory=self.dir)
        b = create_case(demo_form(), set(self.src.list_case_ids()), directory=self.dir)
        self.assertEqual((a["case_id"], b["case_id"]), ("CASE-2001", "CASE-2002"))

    def test_validation(self):
        bad = [
            ("crm_amount", 60000.0), ("crm_amount", "-5"), ("crm_amount", "1.234"), ("close_date", "14/03/2026"),
            ("split_pct", "150"), ("rep_email", "not-an-email"), ("period", "2030-Q9"), ("stage", "won"),
            ("payments", [{"amount": "1.00", "value_date": "2026-01-01"}] * 21), ("rep_name", "<script>alert(1)</script>"),
            ("claimed_shortfall", None),
        ]
        for key, value in bad:
            with self.subTest(key=key, value=str(value)[:30]):
                form = demo_form()
                form[key] = value
                with self.assertRaises(IntakeError):
                    spec_from_form(form, "CASE-2001")
        form = demo_form()
        form["invoice_amount"], form["contract_tcv"], form["amendment"] = "", "", None
        with self.assertRaises(IntakeError):
            spec_from_form(form, "CASE-2001")  # payments without an invoice


class IntakeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from payproof.server import App, make_server
        cls.dir = Path(tempfile.mkdtemp())
        cls.app = App(LocalFixtureSource(user_dir=cls.dir), audit_path=None)
        cls.srv = make_server(cls.app)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def call(self, method, path, user, body=None):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-Demo-User": user, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def test_file_dispute_end_to_end(self):
        st, tpl = self.call("GET", "/api/intake/template?from=CASE-1001", "ana")
        self.assertEqual(st, 200)
        self.assertEqual(self.call("POST", "/api/cases", "rep", tpl["form"])[0], 403)
        self.assertEqual(self.call("POST", "/api/cases", "fin", tpl["form"])[0], 403)
        bad = {**tpl["form"], "crm_amount": "abc"}
        st, err = self.call("POST", "/api/cases", "ana", bad)
        self.assertEqual((st, err["error"]), (422, "INVALID_INPUT"))
        st, made = self.call("POST", "/api/cases", "ana", tpl["form"])
        self.assertEqual((st, made["proof_status"], made["action"]), (201, "VERIFIED", "PREPARE_PAYROLL_ADJUSTMENT"))
        st, queue = self.call("GET", "/api/cases", "ana")
        self.assertEqual(queue[0]["case_id"], "CASE-1001")
        self.assertIn(made["case_id"], [c["case_id"] for c in queue])
        # the filed case goes through the same approval gate
        st, act = self.call("POST", f"/api/cases/{made['case_id']}/actions", "ana")
        self.assertEqual((st, act["state"]), (201, "AWAITING_APPROVAL"))

    def test_benchmark_run_permission(self):
        self.assertEqual(self.call("POST", "/api/benchmark/run", "rep")[0], 403)

    def test_deck_and_images_served(self):
        with urllib.request.urlopen(self.base + "/deck", timeout=10) as r:
            self.assertIn(b"PayProof", r.read())
        with urllib.request.urlopen(self.base + "/img/01-decision-room.png", timeout=10) as r:
            self.assertEqual(r.headers["Content-Type"], "image/png")
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/img/../../payproof/server.py", timeout=10).close()


if __name__ == "__main__":
    unittest.main()
