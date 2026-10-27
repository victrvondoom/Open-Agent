"""RECLAIM bridge contract: tenant principals, honest status, no unsafe retries, strict response contracts."""

import io
import json
import os
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from payproof import reclaim_bridge as rb


def resp(obj, raw=None):
    m = MagicMock()
    m.read.return_value = raw if raw is not None else json.dumps(obj).encode()
    m.__enter__.return_value = m
    m.__exit__.return_value = False
    return m


def http_error(code):
    return urllib.error.HTTPError("http://reclaim.test", code, "err", {}, io.BytesIO(b'{"detail":"x"}'))


AGENT_OK = {"case_id": "c1", "status": "ready_for_human_review", "evidence_summary": "e", "research_summary": "r",
            "strategy": "s", "appeal_draft": "a", "review_notes": ["n"], "citations": ["x"], "agent_trace": [{"agent": "planner"}],
            "structured_citations": [{"title": "invented by nobody"}], "final_report": "not part of AgentRunResponse"}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        rb._STATUS.update(last_ok_at=None, last_error=None, last_error_code=None, calls_ok=0, calls_failed=0, last_endpoint=None)
        self.env = patch.dict(os.environ, {"RECLAIM_API_URL": "http://reclaim.test/api/v1"})
        self.env.start()
        for k in ("SAMPLE_MODE", "RECLAIM_DISABLED", "RECLAIM_TOKEN_NORTH", "RECLAIM_TOKEN_SOUTH"):
            os.environ.pop(k, None)
        self.sleep = patch("payproof.reclaim_bridge.time.sleep")
        self.sleep.start()
        self.client = rb.ReclaimBridgeClient()

    def tearDown(self):
        self.sleep.stop()
        self.env.stop()

    def test_root_strips_api_prefix_for_health(self):
        self.assertEqual(self.client.cfg["root"], "http://reclaim.test")
        with patch("urllib.request.urlopen", return_value=resp({"status": "ok"})) as u:
            self.client.health()
        self.assertEqual(u.call_args[0][0].full_url, "http://reclaim.test/health")

    def test_each_tenant_gets_its_own_principal(self):
        self.assertEqual(rb.principal_for("north"), "payproof-north")
        self.assertNotEqual(rb.principal_for("north"), rb.principal_for("south"))
        with patch.dict(os.environ, {"RECLAIM_TOKEN_NORTH": "jwt-north"}):
            self.assertEqual(rb.principal_for("north"), "jwt-north")
        with self.assertRaises(rb.ReclaimBridgeError):
            rb.principal_for("North Tenant!")

    def test_bearer_is_the_tenant_principal_never_dev_user(self):
        with patch("urllib.request.urlopen", return_value=resp([])) as u:
            self.client.list_cases("south")
        self.assertEqual(u.call_args[0][0].get_header("Authorization"), "Bearer payproof-south")

    def test_status_is_never_live_without_a_successful_call(self):
        self.assertEqual(rb.bridge_status()["state"], "CONFIGURED_UNVERIFIED")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with self.assertRaises(rb.ReclaimBridgeError):
                self.client.list_cases("north")
        self.assertEqual(rb.bridge_status()["state"], "UNAVAILABLE")
        with patch("urllib.request.urlopen", return_value=resp([])):
            self.client.list_cases("north")
        self.assertEqual(rb.bridge_status()["state"], "LIVE")

    def test_non_idempotent_post_is_never_retried(self):
        with patch("urllib.request.urlopen", side_effect=http_error(503)) as u:
            with self.assertRaises(rb.ReclaimBridgeError) as e:
                self.client.run_agents("north", "c1")
        self.assertEqual(u.call_count, 1)
        self.assertEqual(e.exception.code, "RECLAIM_UNREACHABLE")

    def test_get_retries_transient_failures(self):
        with patch("urllib.request.urlopen", side_effect=[http_error(502), resp([{"id": "x"}])]) as u:
            self.assertEqual(len(self.client.list_cases("north")), 1)
        self.assertEqual(u.call_count, 2)

    def test_client_errors_are_not_retried_and_keep_their_code(self):
        for code in (401, 403, 404, 422):
            with patch("urllib.request.urlopen", side_effect=http_error(code)) as u:
                with self.assertRaises(rb.ReclaimBridgeError) as e:
                    self.client.get_case("north", "c1")
            self.assertEqual((u.call_count, e.exception.code), (1, f"RECLAIM_HTTP_{code}"))

    def test_agent_response_contract_is_enforced(self):
        broken = {k: v for k, v in AGENT_OK.items() if k != "citations"}
        with patch("urllib.request.urlopen", return_value=resp(broken)):
            with self.assertRaises(rb.ReclaimBridgeError) as e:
                self.client.run_agents("north", "c1")
        self.assertEqual(e.exception.code, "CONTRACT_VIOLATION")

    def test_fields_outside_the_contract_are_not_passed_through(self):
        with patch("urllib.request.urlopen", return_value=resp(AGENT_OK)):
            out = self.client.run_agents("north", "c1")
        self.assertNotIn("structured_citations", out)
        self.assertNotIn("final_report", out)
        self.assertEqual(out["provenance"], "reclaim-live")
        self.assertEqual(out["citations"], ["x"])

    def test_malformed_json_is_rejected(self):
        with patch("urllib.request.urlopen", return_value=resp(None, raw=b"<html>oops</html>")):
            with self.assertRaises(rb.ReclaimBridgeError) as e:
                self.client.list_cases("north")
        self.assertEqual(e.exception.code, "INVALID_JSON")

    def test_sample_mode_makes_no_network_call(self):
        with patch.dict(os.environ, {"SAMPLE_MODE": "true"}):
            client = rb.ReclaimBridgeClient()
            with patch("urllib.request.urlopen") as u:
                with self.assertRaises(rb.ReclaimBridgeError) as e:
                    client.list_cases("north")
            u.assert_not_called()
            self.assertEqual((e.exception.code, rb.bridge_status()["state"]), ("RECLAIM_DISABLED", "FALLBACK"))

    def test_text_pdf_is_structurally_valid(self):
        pdf = rb.text_pdf("Total paid ₹8,450.00 (card)\nback\\slash", "E-ticket")
        self.assertTrue(pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF"))
        xref_at = int(pdf.rsplit(b"startxref\n", 1)[1].split(b"\n")[0])
        self.assertEqual(pdf[xref_at:xref_at + 4], b"xref")
        self.assertIn(b"INR 8,450.00 \\(card\\)", pdf)
        self.assertIn(b"back\\\\slash", pdf)


if __name__ == "__main__":
    unittest.main()
