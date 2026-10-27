"""
Voice Engine Service — Multilingual speech processing backend.

Architecture inherited from:
- **Bolna**: Plug-and-play STT → LLM → TTS pipeline orchestration
- **Sarvam AI (Saaras/Bulbul)**: 22 Indian language STT/TTS with auto-detection
- **Voice Flow (Canto)**: Transcript cleanup — filler removal, self-correction

This service provides:
1. Language detection from text input
2. Transcript cleanup and formatting
3. Language metadata for all supported Indian languages
"""

import re
import unicodedata
from typing import Optional

# ─── All 22 Scheduled Indian Languages + English ────────────────────────
INDIAN_LANGUAGES = [
    {"code": "en-IN", "name": "English",   "native_name": "English",      "script": "Latin",      "family": "Indo-European"},
    {"code": "hi-IN", "name": "Hindi",     "native_name": "हिन्दी",          "script": "Devanagari", "family": "Indo-Aryan"},
    {"code": "bn-IN", "name": "Bengali",   "native_name": "বাংলা",          "script": "Bengali",    "family": "Indo-Aryan"},
    {"code": "ta-IN", "name": "Tamil",     "native_name": "தமிழ்",          "script": "Tamil",      "family": "Dravidian"},
    {"code": "te-IN", "name": "Telugu",    "native_name": "తెలుగు",         "script": "Telugu",     "family": "Dravidian"},
    {"code": "kn-IN", "name": "Kannada",   "native_name": "ಕನ್ನಡ",          "script": "Kannada",    "family": "Dravidian"},
    {"code": "ml-IN", "name": "Malayalam", "native_name": "മലയാളം",        "script": "Malayalam",  "family": "Dravidian"},
    {"code": "mr-IN", "name": "Marathi",   "native_name": "मराठी",           "script": "Devanagari", "family": "Indo-Aryan"},
    {"code": "gu-IN", "name": "Gujarati",  "native_name": "ગુજરાતી",        "script": "Gujarati",   "family": "Indo-Aryan"},
    {"code": "pa-IN", "name": "Punjabi",   "native_name": "ਪੰਜਾਬੀ",          "script": "Gurmukhi",   "family": "Indo-Aryan"},
    {"code": "or-IN", "name": "Odia",      "native_name": "ଓଡ଼ିଆ",          "script": "Odia",       "family": "Indo-Aryan"},
    {"code": "as-IN", "name": "Assamese",  "native_name": "অসমীয়া",        "script": "Bengali",    "family": "Indo-Aryan"},
    {"code": "ur-IN", "name": "Urdu",      "native_name": "اردو",           "script": "Arabic",     "family": "Indo-Aryan"},
    {"code": "mai-IN","name": "Maithili",  "native_name": "मैथिली",          "script": "Devanagari", "family": "Indo-Aryan"},
    {"code": "sat-IN","name": "Santali",   "native_name": "ᱥᱟᱱᱛᱟᱞᱤ",        "script": "Ol Chiki",   "family": "Austroasiatic"},
    {"code": "ks-IN", "name": "Kashmiri",  "native_name": "कॉशुर",          "script": "Arabic",     "family": "Indo-Aryan"},
    {"code": "ne-IN", "name": "Nepali",    "native_name": "नेपाली",          "script": "Devanagari", "family": "Indo-Aryan"},
    {"code": "sd-IN", "name": "Sindhi",    "native_name": "سنڌي",           "script": "Arabic",     "family": "Indo-Aryan"},
    {"code": "doi-IN","name": "Dogri",     "native_name": "डोगरी",           "script": "Devanagari", "family": "Indo-Aryan"},
    {"code": "kok-IN","name": "Konkani",   "native_name": "कोंकणी",          "script": "Devanagari", "family": "Indo-Aryan"},
    {"code": "mni-IN","name": "Manipuri",  "native_name": "মৈতৈলোন্",        "script": "Meitei",     "family": "Sino-Tibetan"},
    {"code": "brx-IN","name": "Bodo",      "native_name": "बड़ो",            "script": "Devanagari", "family": "Sino-Tibetan"},
    {"code": "sa-IN", "name": "Sanskrit",  "native_name": "संस्कृतम्",        "script": "Devanagari", "family": "Indo-Aryan"},
]

# Script detection ranges (Unicode blocks)
SCRIPT_RANGES = {
    "Devanagari": (0x0900, 0x097F),
    "Bengali":    (0x0980, 0x09FF),
    "Tamil":      (0x0B80, 0x0BFF),
    "Telugu":     (0x0C00, 0x0C7F),
    "Kannada":    (0x0C80, 0x0CFF),
    "Malayalam":  (0x0D00, 0x0D7F),
    "Gujarati":   (0x0A80, 0x0AFF),
    "Gurmukhi":   (0x0A00, 0x0A7F),
    "Odia":       (0x0B00, 0x0B7F),
    "Arabic":     (0x0600, 0x06FF),
    "Ol Chiki":   (0x1C50, 0x1C7F),
    "Meitei":     (0xABC0, 0xABFF),
}

# Filler patterns per language
FILLER_PATTERNS = [
    re.compile(r"\b(um+|uh+|ah+|er+|hmm+|hm+|like|you know|basically|actually|so+|well)\b", re.IGNORECASE),
    re.compile(r"\b(मतलब|अच्छा|वो|ऐसा|बस|हां|ना|तो)\b"),    # Hindi
    re.compile(r"\b(அதாவது|சரி|அப்போ|இல்லை)\b"),            # Tamil
    re.compile(r"\b(అంటే|సరే|అప్పుడు)\b"),                    # Telugu
    re.compile(r"\b(म्हणजे|बरोबर|मग)\b"),                      # Marathi
    re.compile(r"\b(মানে|আচ্ছা|তো)\b"),                         # Bengali
]


def detect_language(text: str) -> dict:
    """
    Detect the dominant script/language in a text using Unicode block analysis.
    Inspired by Sarvam Saaras V4 auto-detection.
    """
    script_counts: dict[str, int] = {}
    for char in text:
        cp = ord(char)
        for script, (start, end) in SCRIPT_RANGES.items():
            if start <= cp <= end:
                script_counts[script] = script_counts.get(script, 0) + 1
                break

    if not script_counts:
        # Default to English if no Indic script detected
        return INDIAN_LANGUAGES[0]

    dominant_script = max(script_counts, key=script_counts.get)  # type: ignore
    
    # Find matching language
    for lang in INDIAN_LANGUAGES:
        if lang["script"] == dominant_script:
            return lang

    return INDIAN_LANGUAGES[0]


def clean_transcript(raw: str) -> str:
    """
    Voice Flow Canto-style transcript cleanup:
    1. Remove filler words
    2. Handle self-corrections
    3. Clean up whitespace
    4. Auto-capitalize and punctuate
    """
    cleaned = raw

    # Self-correction patterns
    cleaned = re.sub(
        r"(\w+(?:\s+\w+){0,3}),?\s*(?:no|nah|wait|sorry|I mean|actually)\s+(\w+(?:\s+\w+){0,5})",
        r"\2",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove fillers
    for pattern in FILLER_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Clean whitespace
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    # Auto-capitalize
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    # Ensure ending punctuation
    if cleaned and not re.search(r"[.!?।]$", cleaned):
        cleaned += "."

    return cleaned


def get_all_languages() -> list[dict]:
    """Return all supported Indian languages with metadata."""
    return INDIAN_LANGUAGES


def get_primary_languages() -> list[dict]:
    """Return primary languages with full STT+TTS coverage (Sarvam Saaras/Bulbul level)."""
    primary_codes = {
        "en-IN", "hi-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN",
        "ml-IN", "mr-IN", "gu-IN", "pa-IN", "or-IN", "ur-IN",
    }
    return [lang for lang in INDIAN_LANGUAGES if lang["code"] in primary_codes]
