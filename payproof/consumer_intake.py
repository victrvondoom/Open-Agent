"""Consumer dispute intake: strict validation of claimant-supplied fields.

Free text may not carry markup or control characters and is size-bounded; identifiers must match
strict patterns; money must be an exact decimal within range. Injection screening is done separately
by the Meterless Scout guard before this runs. Documents are plain text (rendered to PDF only when
they are uploaded into RECLAIM's vault); binary uploads are not accepted here.
"""

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .reclaim_bridge import DOMAINS

REF_RE = re.compile(r"[A-Z0-9]{6}")
FLIGHT_RE = re.compile(r"[A-Z0-9]{2}-\d{3,4}")
TEXT_RE = re.compile(r"[^<>\x00-\x08\x0b\x0c\x0e-\x1f\x7f]*")
DOC_KINDS = {"e_ticket", "cancellation_notice", "refund_notice", "bank_statement", "customer_note"}
MAX_MONEY = Decimal("1000000")
MAX_DOCS = 5


class ConsumerIntakeError(ValueError):
    def __init__(self, field, message):
        super().__init__(f"{field}: {message}")
        self.field = field


def _text(form, key, max_len, required=True, default=""):
    v = form.get(key, default)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise ConsumerIntakeError(key, "required")
        return default
    if not isinstance(v, str) or len(v) > max_len or not TEXT_RE.fullmatch(v):
        raise ConsumerIntakeError(key, f"must be plain text up to {max_len} characters (no markup)")
    return v.strip()


def _money(form, key):
    try:
        d = Decimal(str(form.get(key, "0")).replace(",", ""))
    except InvalidOperation:
        raise ConsumerIntakeError(key, "must be an amount")
    if not d.is_finite() or d < 0 or d > MAX_MONEY:
        raise ConsumerIntakeError(key, "must be between 0 and 1,000,000")
    return f"{d.quantize(Decimal('0.01'))}"


def claim_from_form(form: dict, user: dict, bookings: list[dict]) -> dict:
    """A claim case ready for ConsumerSource.create_case (case_id/claim id are allocated there)."""
    ref = _text(form, "booking_ref", 6).upper()
    if not REF_RE.fullmatch(ref):
        raise ConsumerIntakeError("booking_ref", "must be the 6-character booking reference (PNR)")
    domain = _text(form, "domain", 32, required=False, default="airlines")
    if domain not in DOMAINS:
        raise ConsumerIntakeError("domain", f"must be one of {sorted(DOMAINS)}")
    claimant_id = user.get("claimant_id") or _text(form, "claimant_id", 32, required=False, default="")
    if claimant_id and not re.fullmatch(r"CUST-[A-Za-z0-9-]{1,24}", claimant_id):
        raise ConsumerIntakeError("claimant_id", "must look like CUST-1234")
    booking = next((b for b in bookings if b.get("booking_ref") == ref), None)
    institution = booking["carrier"] if booking else _text(form, "institution_name", 160)
    flight = (booking or {}).get("flight_no") or _text(form, "flight_no", 8, required=False)
    if flight and not FLIGHT_RE.fullmatch(flight):
        raise ConsumerIntakeError("flight_no", "must look like SF-241")
    docs = form.get("documents") or []
    if not isinstance(docs, list) or len(docs) > MAX_DOCS:
        raise ConsumerIntakeError("documents", f"at most {MAX_DOCS} documents")
    documents = []
    for i, doc in enumerate(docs, 1):
        if not isinstance(doc, dict) or doc.get("kind") not in DOC_KINDS:
            raise ConsumerIntakeError(f"documents[{i}].kind", f"must be one of {sorted(DOC_KINDS)}")
        documents.append({"id": f"DOC-NEW-{i}", "kind": doc["kind"], "title": _text(doc, "title", 120, required=False, default=doc["kind"]),
                          "text": _text(doc, "text", 4000), "provenance": "claimant-upload (intake)"})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    narrative = _text(form, "narrative", 2000)
    title = _text(form, "title", 160, required=False, default=f"{institution} {flight or ref} - consumer dispute")
    return {"domain": domain, "tenant_id": user["tenant"], "jurisdiction": "IN", "title": title, "institution_name": institution,
            "tags": ["user-filed"], "as_of": now, "as_of_mode": "live",
            "dispute": {"id": "CLM-NEW", "type": "consumer_claim", "claimant_id": claimant_id or f"CUST-{user['id']}",
                        "claimant_name": _text(form, "claimant_name", 120), "booking_ref": ref, "flight_no": flight,
                        "claim_type": "cancellation_refund_and_compensation", "claimed_refund": _money(form, "claimed_refund"),
                        "claimed_compensation": _money(form, "claimed_compensation"), "currency": "INR", "narrative": narrative,
                        "filed_at": now, "effective_at": now, "recorded_at": now, "filed_by": user["id"]},
            "documents": documents, "agent_run": None}
