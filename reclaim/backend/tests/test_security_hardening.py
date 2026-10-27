"""Regression tests for the backend security audit fixes.

Each test drives the exploit path the audit described and asserts it is
closed; the dev-mode test at the end guards the no-token `dev-user` flow the
Next.js frontend relies on. Every store the action fabric writes to is
redirected to tmp_path (see the `isolated_stores` fixture in conftest.py).
"""
from __future__ import annotations

import importlib
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import claims_to_user
from app.database.postgres.repositories import case_repository
from app.main import app
from app.services.connectors import email_delivery
from app.services.connectors.approval_gate import ActionApprovalGate, approval_gate
from app.services.connectors.email_delivery import EmailComplaintConnector
from app.services.connectors.models import ExecutionMode

API = "/api/v1"
AVIATION = "reclaim.connectors.aviation_refund"
EMAIL = "reclaim.connectors.email_delivery"
OUTSIDE_CANARY = "CANARY-OUTSIDE-DOCUMENT-ROOT-7f3a"


@pytest.fixture
def client():
    # The rate limiter keys on X-Forwarded-For; a bucket per test keeps this
    # request-heavy module from tripping, or draining, the suite's shared 60/min window.
    return TestClient(app, headers={"x-forwarded-for": f"security-tests-{uuid4().hex}"})


def _email_payload(case_id: str, recipient: str = "nodal.officer@insurer.example") -> dict:
    return {
        "recipient_email": recipient,
        "subject": "Formal grievance",
        "body": "Formal complaint regarding an unresolved refund dispute.",
        "case_id": case_id,
    }


def _prepare(client, headers, connector_id, action_id, case_id, payload, mode="sandbox") -> dict:
    res = client.post(
        f"{API}/connectors/{connector_id}/prepare",
        headers=headers,
        json={"action_id": action_id, "case_id": case_id, "payload": payload, "execution_mode": mode},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _approve(client, headers, prepared) -> str:
    res = client.post(
        f"{API}/connectors/approve",
        headers=headers,
        json={"prepared_action": prepared, "consent_statement": "I explicitly authorize this action."},
    )
    assert res.status_code == 200, res.text
    return res.json()["approval_token"]


def _execute(client, headers, connector_id, body) -> object:
    return client.post(
        f"{API}/connectors/{connector_id}/execute",
        headers=headers,
        json={"idempotency_key": f"idemp-{uuid4().hex}", **body},
    )


def _outbox(stores) -> list[dict]:
    path = stores / "email_outbox.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---- 1. pdf_parser: no arbitrary file read ---------------------------------

@pytest.fixture
def pdf_parser_tool(monkeypatch):
    """builtin.py registers its tools only when imported, and nothing in the
    app imports it today, so the route answers 'Unknown tool'. Register
    pdf_parser into a throwaway registry dict to exercise the route as it
    would behave once tools are wired in."""
    from app.agents.tools.registry import tool_registry

    monkeypatch.setattr(tool_registry, "_tools", {})
    from app.agents.tools.builtin import pdf_parser  # a first import registers into the throwaway dict

    tool_registry.register("pdf_parser", "Extract text from a document in the document storage root.", pdf_parser)


@pytest.fixture
def document_root(tmp_path, monkeypatch, pdf_parser_tool):
    root = tmp_path / "document_root"
    (root / "banking").mkdir(parents=True)
    (root / "banking" / "rbi_circular.txt").write_text("RBI circular: refunds within 7 days.", encoding="utf-8")
    (root / "settings.json").write_text('{"not": "a document"}', encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text(OUTSIDE_CANARY, encoding="utf-8")
    monkeypatch.setenv("DOCUMENT_STORAGE_ROOT", str(root))
    return root, secret


def _pdf_parser(client, headers, file_path) -> dict:
    res = client.post(
        f"{API}/intelligence/tools/pdf_parser/call",
        headers=headers,
        json={"arguments": {"file_path": file_path}},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_pdf_parser_refuses_paths_outside_document_root(client, jwt_auth, document_root):
    _, secret = document_root
    headers = jwt_auth("user-reader")
    for attempt in (str(secret), "../outside/secret.txt", "banking/../../outside/secret.txt"):
        body = _pdf_parser(client, headers, attempt)
        assert body["ok"] is False, attempt
        assert OUTSIDE_CANARY not in json.dumps(body)
    # inside the root but not a document type
    assert _pdf_parser(client, headers, "settings.json")["ok"] is False


def test_pdf_parser_function_refuses_outside_paths_before_touching_them(document_root):
    import asyncio

    from app.agents.tools.builtin import pdf_parser

    _, secret = document_root
    with pytest.raises(PermissionError):
        asyncio.run(pdf_parser(str(secret)))
    # same refusal whether or not the outside file exists: no existence oracle
    with pytest.raises(PermissionError):
        asyncio.run(pdf_parser(str(secret.with_name("missing.txt"))))


def test_pdf_parser_does_not_follow_links_out_of_document_root(client, jwt_auth, document_root):
    root, secret = document_root
    link = root / "linked.txt"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted here")
    for attempt in ("linked.txt", str(link)):
        body = _pdf_parser(client, jwt_auth("user-reader"), attempt)
        assert body["ok"] is False, attempt
        assert OUTSIDE_CANARY not in json.dumps(body)


def test_pdf_parser_still_reads_documents_inside_root(client, jwt_auth, document_root):
    root, _ = document_root
    headers = jwt_auth("user-reader")
    for attempt in ("banking/rbi_circular.txt", str(root / "banking" / "rbi_circular.txt")):
        body = _pdf_parser(client, headers, attempt)
        assert body["ok"] is True, body
        assert "refunds within 7 days" in body["result"]["text"]


def test_tool_call_requires_authentication(client, jwt_auth, document_root):
    res = client.post(
        f"{API}/intelligence/tools/pdf_parser/call",
        json={"arguments": {"file_path": "banking/rbi_circular.txt"}},
    )
    assert res.status_code == 401


# ---- 2. execute uses the server-side prepared action -----------------------

def test_client_cannot_switch_off_approval_requirement(client, jwt_auth, owned_case, isolated_stores):
    headers = jwt_auth("user-a")
    case_id = owned_case("user-a")
    unapproved = {"requires_human_approval": False, "approval_state": "not_required"}

    email = _prepare(client, headers, EMAIL, "send_complaint_email", case_id, _email_payload(case_id))
    res = _execute(client, headers, EMAIL, {"prepared_action": {**email, **unapproved}})
    assert res.status_code == 403
    assert "Approval Gate" in res.json()["detail"]

    claim = _prepare(
        client, headers, AVIATION, "submit_airline_claim", case_id,
        {"pnr": "PNR123", "airline": "IndiGo", "claim_package": {"claimed_amount": 17500}},
    )
    res = _execute(client, headers, AVIATION, {"prepared_action": {**claim, **unapproved}})
    assert res.status_code == 403

    assert _outbox(isolated_stores) == []
    assert client.get(f"{API}/connectors/cases/{case_id}/operations", headers=headers).json() == []


def test_execute_rejects_prepared_action_the_server_never_issued(client, jwt_auth, owned_case, isolated_stores):
    headers = jwt_auth("user-a")
    case_id = owned_case("user-a")
    forged = {
        "prepared_action_id": f"prep-forged-{uuid4().hex[:8]}",
        "connector_id": EMAIL,
        "action_id": "send_complaint_email",
        "case_id": case_id,
        "execution_mode": "sandbox",
        "requires_human_approval": False,
        "approval_state": "not_required",
        "parameters": _email_payload(case_id),
        "summary_for_human": "forged",
        "consequences": [],
        "reversibility": True,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    res = _execute(client, headers, EMAIL, {"prepared_action": forged})
    assert res.status_code == 404
    assert _outbox(isolated_stores) == []


def test_prepared_action_and_its_approval_are_private_to_the_owner(client, jwt_auth, owned_case, isolated_stores):
    alice, mallory = jwt_auth("user-alice"), jwt_auth("user-mallory")
    alice_case, mallory_case = owned_case("user-alice"), owned_case("user-mallory")
    prepared = _prepare(client, alice, EMAIL, "send_complaint_email", alice_case, _email_payload(alice_case))
    token = _approve(client, alice, prepared)

    # Mallory replays Alice's approval on a copy re-pointed at her own case and recipient.
    hijack = {**prepared, "case_id": mallory_case, "parameters": _email_payload(mallory_case, "attacker@evil.example")}
    res = _execute(client, mallory, EMAIL, {"prepared_action": hijack, "approval_token": token})
    assert res.status_code == 404
    assert _outbox(isolated_stores) == []

    # ...nor can she approve or execute Alice's action by its id.
    res = client.post(
        f"{API}/connectors/approve",
        headers=mallory,
        json={"prepared_action_id": prepared["prepared_action_id"], "consent_statement": "ok"},
    )
    assert res.status_code == 404
    res = _execute(client, mallory, EMAIL, {"prepared_action_id": prepared["prepared_action_id"], "approval_token": token})
    assert res.status_code == 404
    assert _outbox(isolated_stores) == []


# ---- 3. approval tokens are bound to content --------------------------------

def test_parameters_digest_is_canonical():
    from app.services.connectors.approval_gate import parameters_digest

    assert parameters_digest({"b": 1, "a": {"x": 7500.0, "y": [1, 2]}}) == parameters_digest({"a": {"y": [1, 2], "x": 7500}, "b": 1})
    assert parameters_digest({"a": 1}) != parameters_digest({"a": 2})


def test_approval_token_is_bound_to_case_mode_parameters_and_user(tmp_path):
    gate = ActionApprovalGate(storage_dir=tmp_path)
    connector = EmailComplaintConnector(outbox_dir=tmp_path)
    prepared = connector.prepare_action("send_complaint_email", _email_payload("case-1"), "case-1", "sandbox")
    token = gate.issue_approval(prepared, user_id="user-a", consent_statement="I approve.")

    assert gate.verify_approval(prepared, token) == (True, None)
    tampered = [
        prepared.model_copy(update={"parameters": {**prepared.parameters, "recipient_email": "attacker@evil.example"}}),
        prepared.model_copy(update={"case_id": "case-2"}),
        prepared.model_copy(update={"execution_mode": ExecutionMode.LIVE}),
    ]
    for variant in tampered:
        ok, reason = gate.verify_approval(variant, token)
        assert ok is False, reason
    assert gate.verify_approval(prepared, token, user_id="user-a") == (True, None)
    ok, reason = gate.verify_approval(prepared, token, user_id="user-b")
    assert ok is False and "different user" in reason
    # a flag on the action can't remove a requirement the server policy imposes
    relaxed = prepared.model_copy(update={"requires_human_approval": False})
    assert gate.verify_approval(relaxed, None, required=True)[0] is False


def test_execute_rejects_parameters_changed_after_approval(client, jwt_auth, owned_case, isolated_stores):
    headers = jwt_auth("user-a")
    case_id = owned_case("user-a")
    prepared = _prepare(client, headers, EMAIL, "send_complaint_email", case_id, _email_payload(case_id))
    token = _approve(client, headers, prepared)

    swapped = {**prepared, "parameters": {**prepared["parameters"], "recipient_email": "attacker@evil.example"}}
    res = _execute(client, headers, EMAIL, {"prepared_action": swapped, "approval_token": token})
    assert res.status_code == 403
    assert _outbox(isolated_stores) == []

    # The approved action itself (addressed by id alone) still goes through, to the approved recipient only.
    res = _execute(client, headers, EMAIL, {"prepared_action_id": prepared["prepared_action_id"], "approval_token": token})
    assert res.status_code == 200, res.text
    assert [m["recipient"] for m in _outbox(isolated_stores)] == ["nodal.officer@insurer.example"]


# ---- 4. email connector: real SMTP only when live AND opted in --------------

@pytest.fixture
def smtp_spy(monkeypatch):
    """Swap smtplib.SMTP for a recorder (no network) and set SMTP_HOST the
    way an operator's environment would."""
    connections: list[dict] = []

    class RecordingSMTP:
        def __init__(self, host, port, timeout=None):
            self.record = {"host": host, "sent": []}
            connections.append(self.record)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            self.record["sent"].append(msg["To"])

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", RecordingSMTP)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.invalid")
    for name in ("CONNECTOR_LIVE_EMAIL_ENABLED", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    return connections


def _send_complaint(stores, mode: str):
    connector = EmailComplaintConnector(outbox_dir=stores)
    prepared = connector.prepare_action("send_complaint_email", _email_payload("case-mail"), "case-mail", mode)
    token = approval_gate.issue_approval(prepared, user_id="user-a", consent_statement="I approve.")
    return connector.execute_action(prepared, f"idemp-{uuid4().hex}", token)


# The connector schedules its case-event write via asyncio.get_event_loop(), which warns
# when called synchronously like this; that pre-existing behaviour is not under test here.
_NO_LOOP_WARNING = pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning")


@_NO_LOOP_WARNING
def test_sandbox_email_never_uses_smtp_even_with_smtp_host(isolated_stores, smtp_spy):
    result = _send_complaint(isolated_stores, "sandbox")
    assert smtp_spy == []
    assert result.output_data["delivery_mode"] == "LOCAL_SECURE_TEST_OUTBOX"
    assert len(_outbox(isolated_stores)) == 1


@_NO_LOOP_WARNING
def test_live_email_requires_explicit_opt_in(isolated_stores, smtp_spy, monkeypatch):
    result = _send_complaint(isolated_stores, "live")
    assert smtp_spy == []  # SMTP_HOST alone is not consent to send real mail
    assert result.output_data["delivery_mode"] == "LOCAL_SECURE_TEST_OUTBOX"

    monkeypatch.setenv("CONNECTOR_LIVE_EMAIL_ENABLED", "true")
    result = _send_complaint(isolated_stores, "live")
    assert [c["sent"] for c in smtp_spy] == [["nodal.officer@insurer.example"]]
    assert result.output_data["delivery_mode"] == "LIVE_SMTP_TRANSMISSION"

    smtp_spy.clear()
    _send_complaint(isolated_stores, "sandbox")  # opted in, but a sandbox action stays local
    assert smtp_spy == []


def test_email_health_reports_live_only_when_opted_in(isolated_stores, smtp_spy, monkeypatch):
    connector = EmailComplaintConnector(outbox_dir=isolated_stores)
    assert connector.healthcheck().active_mode == ExecutionMode.SANDBOX
    monkeypatch.setenv("CONNECTOR_LIVE_EMAIL_ENABLED", "true")
    assert connector.healthcheck().active_mode == ExecutionMode.LIVE


# ---- 5. operation status / reconcile: authenticated and owner-scoped --------

def test_operation_status_and_reconcile_are_owner_scoped(client, jwt_auth, owned_case, isolated_stores):
    alice, mallory = jwt_auth("user-alice"), jwt_auth("user-mallory")
    case_id = owned_case("user-alice")
    owned_case("user-mallory")
    prepared = _prepare(
        client, alice, AVIATION, "check_statutory_eligibility", case_id,
        {"airline": "IndiGo", "flight_number": "6E-204", "cancellation_notice_hours": 12, "ticket_amount": 7500},
    )
    res = _execute(client, alice, AVIATION, {"prepared_action": prepared})
    assert res.status_code == 200, res.text
    status_url = f"{API}/connectors/{AVIATION}/operations/{res.json()['operation_id']}"

    for url in (status_url, f"{status_url}/reconcile"):
        assert client.get(url).status_code == 401
        assert client.get(url, headers=mallory).status_code == 404
        assert client.get(url, headers=alice).status_code == 200
    assert client.get(status_url, headers=alice).json()["case_id"] == case_id


# ---- 6. decision optimize: authenticated and owner-scoped ------------------

def test_decision_optimize_requires_auth_and_case_ownership(client, jwt_auth, owned_case, isolated_stores):
    alice, mallory = jwt_auth("user-alice"), jwt_auth("user-mallory")
    case_id = owned_case("user-alice")
    body = {"case_id": case_id, "available_evidence": ["booking_pnr", "cancellation_sms_or_email"]}

    def case_events() -> list[str]:
        return [e["event_type"] for e in case_repository._events if e["case_id"] == case_id]

    assert client.post(f"{API}/decision/optimize", json=body).status_code == 401
    assert client.post(f"{API}/decision/optimize", headers=mallory, json=body).status_code == 404
    assert case_events() == []

    res = client.post(f"{API}/decision/optimize", headers=alice, json=body)
    assert res.status_code == 200, res.text
    assert case_events() == ["decision_optimized"]


# ---- 7 + 8. ingest is admin-only; role only from app_metadata ---------------

@pytest.mark.parametrize("domain", ["telecom", "ecommerce", "government"])
def test_domain_ingest_requires_admin(client, jwt_auth, monkeypatch, domain):
    started: list[str] = []

    async def fake_ingestion() -> None:
        started.append(domain)

    # Never run the real background re-embedding from a test, even if auth regressed.
    monkeypatch.setattr(importlib.import_module(f"app.api.routes.{domain}"), "_run_ingestion", fake_ingestion)
    url = f"{API}/{domain}/ingest"

    assert client.post(url).status_code == 401
    assert client.post(url, headers=jwt_auth("user-plain")).status_code == 403
    assert client.post(url, headers=jwt_auth("user-self-promoted", user_role="admin")).status_code == 403
    assert started == []

    assert client.post(url, headers=jwt_auth("user-admin", app_role="admin")).status_code == 200
    assert started == [domain]


def test_role_comes_only_from_app_metadata():
    assert claims_to_user({"sub": "u1", "user_metadata": {"role": "admin"}})["role"] == "user"
    assert claims_to_user({"sub": "u1", "app_metadata": {}, "user_metadata": {"role": "admin"}})["role"] == "user"
    assert claims_to_user({"sub": "u1", "app_metadata": {"role": "admin"}, "user_metadata": {"role": "user"}})["role"] == "admin"


# ---- dev mode (no token => dev-user) keeps working for the frontend ---------

@pytest.fixture
def dev_mode(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dev_mode_flows_work_without_a_token(client, dev_mode, owned_case, isolated_stores, monkeypatch):
    case_id = owned_case("dev-user")
    prepared = _prepare(client, {}, EMAIL, "send_complaint_email", case_id, _email_payload(case_id))
    token = _approve(client, {}, prepared)
    res = _execute(client, {}, EMAIL, {"prepared_action": prepared, "approval_token": token})
    assert res.status_code == 200, res.text
    assert client.get(f"{API}/connectors/{EMAIL}/operations/{res.json()['operation_id']}").status_code == 200
    assert client.post(f"{API}/decision/optimize", json={"case_id": case_id}).status_code == 200

    async def noop() -> None:
        return None

    monkeypatch.setattr(importlib.import_module("app.api.routes.telecom"), "_run_ingestion", noop)
    assert client.post(f"{API}/telecom/ingest").status_code == 200
