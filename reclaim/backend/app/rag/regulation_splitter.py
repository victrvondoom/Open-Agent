from __future__ import annotations

import hashlib
import re
import uuid
from typing import Callable, Literal
from pydantic import BaseModel, Field


class ChunkOutput(BaseModel):
    chunk_id: str = Field(description="Unique deterministic or stable UUID for chunk")
    document_id: str = Field(description="Source document identifier")
    sequence_number: int = Field(description="0-indexed sequence position in document")
    text: str = Field(description="Text segment content")
    char_length: int = Field(description="Exact measured character length")
    token_length: int = Field(description="Estimated or measured token length")
    start_offset: int = Field(description="Character start offset in source text")
    end_offset: int = Field(description="Character end offset in source text")
    parent_section: str | None = Field(default=None, description="Enclosing legal section, article, or heading")
    language: str = Field(default="en", description="Detected or annotated primary language")
    source_hash: str = Field(description="SHA256 hash of original document content")
    citations: list[str] = Field(default_factory=list, description="Extracted statutory/regulatory citations in this chunk")


# Regular expression to identify statutory/legal patterns that should NOT be broken across periods
STATUTORY_PROTECTION_PATTERN = re.compile(
    r"\b("
    r"(?:Section|Sec\.|Art\.|Article|Clause|Rule|Part|Order|Schedule|Para|Paragraph)\s+\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))*"
    r"|(?:CAR\s+Series\s+[A-Z]\s+Part\s+[IVXLCDM]+)"
    r"|(?:No\.\s*\d+(?:/\d+)*)"
    r"|(?:v\.\s+[A-Z][a-zA-Z0-9_\s]+)"
    r"|(?:\d+\.\d+)"
    r"|(?:Rs\.\s*[\d,]+)"
    r"|(?:₹\s*[\d,]+)"
    r"|(?:[\$€£]\s*[\d,]+(?:\.\d+)?)"
    r")\b",
    re.IGNORECASE,
)

SECTION_HEADING_PATTERN = re.compile(
    r"^(?:Section|Article|Clause|Rule|Part|Chapter)\s+([0-9A-Za-z\.\-\(\)]+)[^\n]*",
    re.MULTILINE | re.IGNORECASE,
)

CITATION_PATTERN = re.compile(
    r"\b((?:Section|Sec\.|Article|Art\.|Rule|Clause)\s+\d+(?:\.\d+)*(?:\([a-zA-Z0-9]+\))*|"
    r"(?:DGCA\s+CAR\s+Series\s+[A-Z]\s+Part\s+[IVXLCDM]+)|"
    r"(?:EU\s*(?:Regulation\s*)?(?:No\.\s*)?261/2004)|"
    r"(?:Consumer\s+Protection\s+Act(?:,\s*\d{4})?)|"
    r"(?:RERA\s+Act(?:,\s*\d{4})?)|"
    r"(?:RBI\s+Circular\s+[\w\d\-\/\.]+)|"
    r"(?:IRDAI\s+Master\s+Circular\s+[\w\d\-\/\.]+))\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    """Detect language script from Unicode ranges."""
    tamil_chars = sum(1 for c in text if "\u0b80" <= c <= "\u0bff")
    devanagari_chars = sum(1 for c in text if "\u0900" <= c <= "\u097f")
    total = len(text.strip())
    if total == 0:
        return "en"
    if tamil_chars / total > 0.15:
        return "ta"
    if devanagari_chars / total > 0.15:
        return "hi"
    return "en"


def estimate_token_count(text: str) -> int:
    """Estimate token count: roughly 4 chars per token in English, higher in non-latin scripts."""
    if not text:
        return 0
    words = text.split()
    return max(len(words), (len(text) + 3) // 4)


class RecursiveRegulationTextSplitter:
    """Recursive, regulation-aware document segmenter that progressively applies

    finer separators and ensures strict chunk-size compliance via empty-string fallback.
    """

    def __init__(
        self,
        max_chunk_size: int = 200,
        overlap: int = 20,
        separators: list[str] | None = None,
        length_function: Literal["char", "token"] = "char",
        preserve_statutory_tokens: bool = True,
    ):
        if overlap >= max_chunk_size:
            raise ValueError(f"Overlap ({overlap}) must be strictly less than max_chunk_size ({max_chunk_size})")
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.length_function = length_function
        self.preserve_statutory_tokens = preserve_statutory_tokens
        self.separators = separators or ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

    def _measure(self, text: str) -> int:
        if self.length_function == "token":
            return estimate_token_count(text)
        return len(text)

    def _protect_statutory_tokens(self, text: str) -> tuple[str, dict[str, str]]:
        """Temporarily mask dots/punctuation in statutory tokens (e.g. 'Section 3.2')

        to prevent accidental splitting on numbers or legal citations.
        """
        mapping: dict[str, str] = {}

        def repl(match: re.Match) -> str:
            token = match.group(0)
            token_id = f"__STATUTORY_TOKEN_{len(mapping)}__"
            mapping[token_id] = token
            return token_id

        protected_text = STATUTORY_PROTECTION_PATTERN.sub(repl, text)
        return protected_text, mapping

    def _unprotect_statutory_tokens(self, text: str, mapping: dict[str, str]) -> str:
        for placeholder, original in mapping.items():
            text = text.replace(placeholder, original)
        return text

    def _recursive_split(self, text: str, separator_idx: int) -> list[str]:
        if not text:
            return []

        if self._measure(text) <= self.max_chunk_size:
            return [text]

        if separator_idx >= len(self.separators):
            # Final fallback: hard slice to enforce strict chunk budget
            chunks: list[str] = []
            step = max(1, self.max_chunk_size - self.overlap)
            for i in range(0, len(text), step):
                chunk = text[i : i + self.max_chunk_size]
                if chunk:
                    chunks.append(chunk)
                if i + self.max_chunk_size >= len(text):
                    break
            return chunks

        sep = self.separators[separator_idx]

        if sep == "":
            # Character-by-character chunking with overlap
            chunks = []
            step = max(1, self.max_chunk_size - self.overlap)
            for i in range(0, len(text), step):
                chunk = text[i : i + self.max_chunk_size]
                if chunk:
                    chunks.append(chunk)
                if i + self.max_chunk_size >= len(text):
                    break
            return chunks

        splits = text.split(sep)
        good_chunks: list[str] = []
        current_doc: list[str] = []
        current_len = 0

        for s in splits:
            if not s and len(splits) > 1:
                continue
            s_len = self._measure(s)

            if s_len > self.max_chunk_size:
                # Need to subdivide this oversized part with finer separators
                if current_doc:
                    merged = sep.join(current_doc)
                    good_chunks.append(merged)
                    current_doc = []
                    current_len = 0
                sub_chunks = self._recursive_split(s, separator_idx + 1)
                good_chunks.extend(sub_chunks)
            else:
                extra = len(sep) if current_doc else 0
                if current_len + s_len + extra <= self.max_chunk_size:
                    current_doc.append(s)
                    current_len += s_len + extra
                else:
                    if current_doc:
                        good_chunks.append(sep.join(current_doc))
                    current_doc = [s]
                    current_len = s_len

        if current_doc:
            good_chunks.append(sep.join(current_doc))

        # Handle overlap merge across good chunks if desired
        return self._enforce_overlap_and_budget(good_chunks, sep)

    def _enforce_overlap_and_budget(self, chunks: list[str], sep: str) -> list[str]:
        final_chunks: list[str] = []
        for i, chunk in enumerate(chunks):
            chunk_len = self._measure(chunk)
            if chunk_len > self.max_chunk_size:
                # Guarantee: if a chunk still exceeds budget, break by next finer separator or char
                sub = self._recursive_split(chunk, self.separators.index(sep) + 1 if sep in self.separators else len(self.separators))
                final_chunks.extend(sub)
            else:
                final_chunks.append(chunk)
        return final_chunks

    def split_text(
        self,
        text: str,
        document_id: str | None = None,
        source_hash: str | None = None,
    ) -> list[ChunkOutput]:
        """Split document text into ordered, regulation-aware, metadata-rich chunks."""
        if not text:
            return []

        doc_id = document_id or f"doc-{uuid.uuid4().hex[:12]}"
        doc_hash = source_hash or hashlib.sha256(text.encode("utf-8")).hexdigest()
        detected_lang = detect_language(text)

        protected_text, mapping = (
            self._protect_statutory_tokens(text) if self.preserve_statutory_tokens else (text, {})
        )

        raw_chunks = self._recursive_split(protected_text, 0)

        # Unprotect statutory tokens and compute exact offsets
        results: list[ChunkOutput] = []
        cursor = 0

        current_parent_section: str | None = None
        for seq, raw_chunk in enumerate(raw_chunks):
            clean_chunk = self._unprotect_statutory_tokens(raw_chunk, mapping)
            if not clean_chunk.strip():
                continue

            # Track section headings
            heading_match = SECTION_HEADING_PATTERN.search(clean_chunk)
            if heading_match:
                current_parent_section = heading_match.group(0).strip()

            # Find start and end offset in original text
            start_offset = text.find(clean_chunk, cursor)
            if start_offset == -1:
                start_offset = cursor
            end_offset = start_offset + len(clean_chunk)
            cursor = max(cursor, start_offset + 1)

            # Find regulatory citations
            found_citations = [m.group(0).strip() for m in CITATION_PATTERN.finditer(clean_chunk)]

            results.append(
                ChunkOutput(
                    chunk_id=f"{doc_id}-chunk-{seq:04d}",
                    document_id=doc_id,
                    sequence_number=seq,
                    text=clean_chunk,
                    char_length=len(clean_chunk),
                    token_length=estimate_token_count(clean_chunk),
                    start_offset=start_offset,
                    end_offset=end_offset,
                    parent_section=current_parent_section,
                    language=detect_language(clean_chunk) or detected_lang,
                    source_hash=doc_hash,
                    citations=list(dict.fromkeys(found_citations)),
                )
            )

        return results
