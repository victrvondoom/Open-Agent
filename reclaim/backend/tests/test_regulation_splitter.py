from __future__ import annotations

import pytest
from app.rag.regulation_splitter import (
    RecursiveRegulationTextSplitter,
    detect_language,
    estimate_token_count,
)


def test_scenario_1_varied_separator_distribution():
    text = (
        "Heading 1: Consumer Justice.\n\n"
        "First paragraph states the initial grievance. The consumer was denied a refund.\n\n"
        "Second paragraph elaborates on the carrier policy; however, no compensation was paid. "
        "Can the consumer file an escalation? Yes, they can! Under Rule 14, an appeal is valid."
    )
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=100, overlap=10)
    chunks = splitter.split_text(text)
    assert len(chunks) >= 4
    for c in chunks:
        assert c.char_length <= 100
        assert c.sequence_number >= 0
        assert c.document_id.startswith("doc-")


def test_scenario_2_long_paragraph_no_newline():
    text = (
        "This is an extraordinarily long paragraph written without any newlines whatsoever where a consumer describes "
        "their journey from purchasing an airline ticket through a third-party aggregator to experiencing a sudden flight cancellation "
        "two hours prior to departure without any hotel accommodation or statutory food voucher being provided by the ground staff "
        "at the airport terminal despite repeated oral requests."
    )
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=150, overlap=15)
    chunks = splitter.split_text(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.char_length <= 150


def test_scenario_3_long_uninterrupted_token():
    # A single token with no whitespace or punctuation longer than max_chunk_size
    text = "A" * 350
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=100, overlap=10)
    chunks = splitter.split_text(text)
    assert len(chunks) >= 4
    for c in chunks:
        assert c.char_length <= 100


def test_scenario_4_text_only_questions():
    text = (
        "Was the flight delayed for more than three hours? "
        "Did the airline provide food and water? "
        "Was an alternate flight offered within twenty-four hours? "
        "Did the passenger accept a travel voucher instead of cash? "
        "Was the cancellation due to extraordinary circumstances?"
    )
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=120, overlap=10)
    chunks = splitter.split_text(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.char_length <= 120
        assert "?" in c.text or len(c.text) > 0


def test_scenario_5_mixed_english_and_tamil():
    text = (
        "Under Consumer Protection Act 2019, the claim must be resolved in 30 days.\n\n"
        "என் விமானம் முன்னறிவிப்பின்றி ரத்து செய்யப்பட்டது. "
        "விமான நிறுவனம் பணத்தைத் திருப்பித் தர மறுத்துவிட்டது. "
        "இதற்கான இழப்பீட்டை நான் கோர விரும்புகிறேன்."
    )
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=150, overlap=15)
    chunks = splitter.split_text(text)
    assert len(chunks) >= 2
    tamil_found = any(c.language == "ta" for c in chunks)
    assert tamil_found


def test_scenario_6_statutory_clauses_with_subsections():
    # Statutory notation like "Section 3.2" should NOT be prematurely broken at the period in "3.2"
    text = (
        "According to DGCA CAR Series M Part IV Section 3.2, the operating airline shall provide alternate flight "
        "or full refund within seven days of cancellation. Under Section 3.2(a), passenger rights are mandatory."
    )
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=200, overlap=20)
    chunks = splitter.split_text(text)
    # The term Section 3.2 must be preserved intact inside chunks
    combined = " ".join(c.text for c in chunks)
    assert "Section 3.2" in combined
    assert any("Section 3.2" in c.citations or "DGCA CAR Series M Part IV" in c.citations for c in chunks)


def test_scenario_7_repeated_text_with_overlap():
    text = "Claim reference #99201. " * 10
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=100, overlap=20)
    chunks = splitter.split_text(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.char_length <= 100


def test_scenario_8_empty_or_malformed_input():
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=200, overlap=20)
    assert splitter.split_text("") == []
    assert splitter.split_text("   \n\n  \t  ") == []


def test_scenario_9_table_and_legal_citations():
    text = (
        "| Delay Window | Statutory Compensation |\n"
        "| < 2 hours    | ₹ 5,000                |\n"
        "| > 2 hours    | ₹ 10,000               |\n\n"
        "Pursuant to EU Regulation 261/2004 and Consumer Protection Act 2019, damages apply."
    )
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=120, overlap=15)
    chunks = splitter.split_text(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.char_length <= 120
    citations = [cit for c in chunks for cit in c.citations]
    assert any("261/2004" in cit or "Consumer Protection Act" in cit for cit in citations)


def test_scenario_10_strict_budget_enforcement():
    text = (
        "The quick brown fox jumps over the lazy dog. " * 20
    )
    splitter = RecursiveRegulationTextSplitter(max_chunk_size=80, overlap=10)
    chunks = splitter.split_text(text)
    assert len(chunks) > 5
    for c in chunks:
        assert c.char_length <= 80, f"Chunk exceeded budget: {c.char_length} > 80"
