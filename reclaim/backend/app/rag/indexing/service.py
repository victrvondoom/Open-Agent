from __future__ import annotations

from app.models.domain import Domain
from app.rag.regulation_splitter import RecursiveRegulationTextSplitter
from app.rag.retrieval.qdrant_service import qdrant_service


class IndexingService:
    """Document text indexing pipeline using recursive statutory regulation splitting."""

    def __init__(self):
        self.splitter = RecursiveRegulationTextSplitter(
            max_chunk_size=400,
            overlap=40,
            preserve_statutory_tokens=True,
        )

    async def index_document_text(self, domain: Domain, document_id: str, text: str, metadata: dict) -> int:
        if not text or not text.strip():
            return 0

        chunk_outputs = self.splitter.split_text(text, document_id=document_id)
        if not chunk_outputs:
            return 0

        chunks = [c.text for c in chunk_outputs]

        # Extract all statutory citations discovered across chunks
        extracted_citations = []
        for c in chunk_outputs:
            extracted_citations.extend(c.citations)

        enriched_metadata = dict(metadata)
        if extracted_citations:
            enriched_metadata["extracted_citations"] = sorted(list(set(extracted_citations)))

        return await qdrant_service.upsert_chunks(domain, document_id, chunks, enriched_metadata)


indexing_service = IndexingService()
