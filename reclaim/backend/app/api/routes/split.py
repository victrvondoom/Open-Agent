from __future__ import annotations

from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.rag.regulation_splitter import ChunkOutput, RecursiveRegulationTextSplitter

router = APIRouter()


class SplitRequest(BaseModel):
    text: str = Field(description="Raw text to be split")
    document_id: str | None = Field(default=None, description="Optional document ID")
    max_chunk_size: int = Field(default=200, ge=20, le=5000, description="Maximum characters or tokens per chunk")
    overlap: int = Field(default=20, ge=0, description="Character or token overlap between adjacent chunks")
    length_function: Literal["char", "token"] = Field(default="char", description="Measurement function")
    preserve_statutory_tokens: bool = Field(default=True, description="Whether to protect legal citations and decimal sections")


class SplitResponse(BaseModel):
    total_chunks: int
    max_chunk_measured: int
    input_chars: int
    document_id: str
    chunks: list[ChunkOutput]


@router.post("", response_model=SplitResponse)
async def split_document(request: SplitRequest) -> SplitResponse:
    if request.overlap >= request.max_chunk_size:
        raise HTTPException(status_code=400, detail="Overlap must be strictly less than max_chunk_size")

    splitter = RecursiveRegulationTextSplitter(
        max_chunk_size=request.max_chunk_size,
        overlap=request.overlap,
        length_function=request.length_function,
        preserve_statutory_tokens=request.preserve_statutory_tokens,
    )
    chunks = splitter.split_text(request.text, document_id=request.document_id)
    max_measured = max((c.char_length for c in chunks), default=0)
    doc_id = chunks[0].document_id if chunks else (request.document_id or "empty")

    return SplitResponse(
        total_chunks=len(chunks),
        max_chunk_measured=max_measured,
        input_chars=len(request.text),
        document_id=doc_id,
        chunks=chunks,
    )
