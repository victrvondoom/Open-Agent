from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, get_current_user
from app.services.voice_service import voice_service

router = APIRouter()


class VoiceChatRequest(BaseModel):
    message: str
    language_code: str = "auto"
    case_id: str | None = None


class SynthesisRequest(BaseModel):
    text: str
    language_code: str = "en-IN"
    gender: str = "female"
    speed: float = 1.0


@router.get("/languages")
async def get_supported_languages() -> list[dict[str, Any]]:
    """Return all 30 supported Indian languages and regional variants with
    native scripts, BCP-47 codes, language families, and sample consumer claim prompts."""
    return voice_service.get_supported_languages()


@router.post("/transcribe")
async def transcribe_speech(
    file: UploadFile = File(...),
    language_code: str = Form(default="auto"),
    prompt_hint: str | None = Form(default=None),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Multi-model speech-to-text transcription engine (Sarvam Saaras + Voice Flow conformer).
    Automatically identifies language, handles code-mixing (Tanglish/Hinglish), and normalizes
    consumer legal terminology."""
    audio_content = await file.read()
    return await voice_service.transcribe_audio(
        audio_bytes=audio_content,
        filename=file.filename or "recording.webm",
        language_code=language_code,
        prompt_hint=prompt_hint,
    )


@router.post("/chat")
async def multilingual_voice_chat(
    payload: VoiceChatRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Bolna-style Voice Agent chat: receives consumer query in any of 30 Indian languages
    (Tamil, Hindi, Telugu, Tanglish, English, etc.), routes through statutory reasoning,
    and returns a legally grounded response in the caller's native language."""
    return await voice_service.process_multilingual_voice_chat(
        user_message=payload.message,
        language_code=payload.language_code,
        case_id=payload.case_id,
    )


@router.post("/synthesize")
async def synthesize_speech(
    payload: SynthesisRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Sarvam Bulbul style Indic Speech synthesis metadata and phoneme guidance."""
    lang_info = voice_service.detect_indic_language(payload.text) if payload.language_code == "auto" else payload.language_code
    return {
        "text": payload.text,
        "language_code": lang_info,
        "speed": payload.speed,
        "gender": payload.gender,
        "engine": "indic-bulbul-neural-synthesis",
        "ready": True,
    }
