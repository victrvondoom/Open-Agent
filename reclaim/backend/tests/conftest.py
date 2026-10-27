import os

# Set environment to test before any imports load settings
os.environ["ENVIRONMENT"] = "test"
os.environ["DISABLE_EXTERNAL_LLM"] = "true"
# The supervisor LLM-call counts assume the response agent LLM is off. Pin it here so the
# suite does not depend on a developer's local .env (which is git-ignored and not shipped).
os.environ["RESPONSE_AGENT_LLM_ENABLED"] = "false"
# Pin the default provider so existing tests are hermetic regardless of the
# developer's local .env LLM_PROVIDER choice; provider-specific behavior is
# covered explicitly in test_llm_providers.py. NVIDIA is the real active
# production provider (all reindexed knowledge-base collections are
# 1024-dim NVIDIA embeddings) — pinning tests to it too keeps the hash-fallback
# dimension used in test mode consistent with what's actually indexed.
os.environ.setdefault("LLM_PROVIDER", "nvidia")

import pytest

TEST_JWT_SECRET = "test-supabase-jwt-secret-for-proxy"


@pytest.fixture
def jwt_auth(monkeypatch):
    """Production-mode auth (no dev-user fallback): requests must carry an
    HS256 Supabase-style JWT signed with a test secret. Yields a factory that
    builds Authorization headers for a subject and optional roles."""
    from datetime import datetime, timedelta, timezone

    import jwt

    from app.core.config import get_settings

    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    def headers(sub: str, app_role: str | None = None, user_role: str | None = None) -> dict[str, str]:
        exp = datetime.now(timezone.utc) + timedelta(hours=1)
        claims: dict = {"sub": sub, "email": f"{sub}@example.com", "aud": "authenticated", "exp": int(exp.timestamp())}
        if app_role:
            claims["app_metadata"] = {"role": app_role}
        if user_role:
            claims["user_metadata"] = {"role": user_role}
        return {"Authorization": f"Bearer {jwt.encode(claims, TEST_JWT_SECRET, algorithm='HS256')}"}

    yield headers
    get_settings.cache_clear()


@pytest.fixture
def owned_case(monkeypatch):
    """Factory: register a case owned by `user_id` in the in-memory case store
    only -- removed after the test and never written to the tracked jsonl store."""
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.database.postgres.repositories import case_repository
    from app.models.domain import Domain
    from app.schemas.cases import CaseStatus

    def make(user_id: str, domain: Domain = Domain.AIRLINES, institution_name: str = "IndiGo") -> str:
        case_id = f"case-test-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        monkeypatch.setitem(case_repository._cases, case_id, {
            "id": case_id,
            "user_id": user_id,
            "domain": domain,
            "title": "Test dispute",
            "institution_name": institution_name,
            "summary": "Flight cancelled without refund.",
            "jurisdiction": "IN",
            "status": CaseStatus.INTAKE,
            "created_at": now,
            "updated_at": now,
        })
        return case_id

    return make


@pytest.fixture
def isolated_stores(tmp_path, monkeypatch):
    """Point the action fabric (prepared actions, approvals, audit, operations,
    email outbox) and case-event persistence at tmp_path, so tests never write
    to the tracked datasets/app_store files."""
    from app.database.postgres.repositories import LocalRepositoryStore, case_repository
    from app.services.connectors import storage
    from app.services.connectors.approval_gate import approval_gate
    from app.services.connectors.registry import connector_registry

    monkeypatch.setattr(case_repository, "local", LocalRepositoryStore(tmp_path / "app_store"))
    monkeypatch.setattr(storage, "OPERATIONS_FILE", tmp_path / "connector_operations.jsonl")
    for attr in ("tokens_file", "audit_file", "prepared_file"):
        monkeypatch.setattr(approval_gate, attr, tmp_path / getattr(approval_gate, attr).name)
    email_connector = connector_registry.get("reclaim.connectors.email_delivery")
    monkeypatch.setattr(email_connector, "outbox_file", tmp_path / "email_outbox.jsonl")
    return tmp_path
