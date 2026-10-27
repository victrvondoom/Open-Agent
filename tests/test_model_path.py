"""Exercises the OpenAI-compatible model path against a local stub (not a live Nemotron)."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from payproof.llm import ModelClient
from payproof.sources import LocalFixtureSource, load_plans
from payproof.workflow import investigate

CLAIMS = {"claims": [
    {"text": "Commission due is $4,300.00 based on collected cash.", "cites": ["PAY-44120", "PAY-44987"]},
    {"text": "The rep is owed $3,000.00 per the signed contract.", "cites": ["CTR-9999"]},
    {"text": "A bonus of $750.00 also applies.", "cites": ["OPP-5521"]},
]}


class Stub(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        Stub.calls += 1
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["temperature"] == 0
        out = json.dumps({"model": "stub-nemotron", "choices": [{"message": {"content": json.dumps(CLAIMS)}}],
                          "usage": {"total_tokens": 42}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class ModelPathTests(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        os.environ["LLM_BASE_URL"] = f"http://127.0.0.1:{self.srv.server_port}/v1"

    def tearDown(self):
        self.srv.shutdown()
        os.environ.pop("LLM_BASE_URL", None)

    def test_validator_drops_hallucinated_claims_and_model_cannot_change_money(self):
        r = investigate(LocalFixtureSource().load_case("CASE-1001"), load_plans(), model=ModelClient())
        texts = [c["text"] for c in r["narrative"]]
        self.assertIn(CLAIMS["claims"][0]["text"], texts)
        reasons = [u["reason"] for u in r["validation"]["unsupported_claims"]]
        self.assertTrue(any("CTR-9999" in x for x in reasons))
        self.assertTrue(any("750.00" in x for x in reasons))
        self.assertEqual(r["calculation"]["due"], "4300.00")
        self.assertEqual(r["proposed_action"]["amount"], "1100.00")
        self.assertEqual([m["status"] for m in r["telemetry"]["model_calls"]], ["ok", "ok"])
        self.assertLessEqual(Stub.calls, 2)


if __name__ == "__main__":
    unittest.main()
