/**
 * voice-engine.ts — Multilingual Voice Engine
 *
 * Architecture inspired by:
 * - **Bolna**: Plug-and-play STT → LLM → TTS pipeline with mid-call language switching
 * - **Sarvam AI (Saaras/Bulbul)**: 22 Indian language STT/TTS, auto-detect, code-mixing
 * - **Voice Flow (Canto)**: Intelligent cleanup — filler removal, self-correction, auto-punctuation
 *
 * This engine orchestrates:
 * 1. Browser Web Speech API as primary STT (fallback for all supported locales)
 * 2. Sarvam Saaras-style auto language detection
 * 3. Voice-flow-style transcript cleanup (filler removal, self-correction)
 * 4. Bolna-style orchestration pipeline
 * 5. Web Speech Synthesis API for TTS with language-appropriate voices
 */

// ─── All 22 Scheduled Indian Languages + English ───────────────────────────
export interface VoiceLanguage {
  code: string;          // BCP-47 language tag
  name: string;          // English name
  nativeName: string;    // Native script name
  sttLocale: string;     // Web Speech API locale code
  ttsLang: string;       // SpeechSynthesis language
  script: string;        // Writing script
  family: string;        // Language family grouping
}

export const INDIAN_LANGUAGES: VoiceLanguage[] = [
  { code: "en-IN", name: "English (India)", nativeName: "English",       sttLocale: "en-IN",  ttsLang: "en-IN",  script: "Latin",      family: "Indo-European" },
  { code: "ta-IN", name: "Tamil",           nativeName: "தமிழ்",          sttLocale: "ta-IN",  ttsLang: "ta-IN",  script: "Tamil",      family: "Dravidian" },
  { code: "hi-IN", name: "Hindi",           nativeName: "हिन्दी",          sttLocale: "hi-IN",  ttsLang: "hi-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "te-IN", name: "Telugu",          nativeName: "తెలుగు",         sttLocale: "te-IN",  ttsLang: "te-IN",  script: "Telugu",     family: "Dravidian" },
  { code: "kn-IN", name: "Kannada",         nativeName: "ಕನ್ನಡ",          sttLocale: "kn-IN",  ttsLang: "kn-IN",  script: "Kannada",    family: "Dravidian" },
  { code: "ml-IN", name: "Malayalam",       nativeName: "മലയാളം",        sttLocale: "ml-IN",  ttsLang: "ml-IN",  script: "Malayalam",  family: "Dravidian" },
  { code: "bn-IN", name: "Bengali",         nativeName: "বাংলা",          sttLocale: "bn-IN",  ttsLang: "bn-IN",  script: "Bengali",    family: "Indo-Aryan" },
  { code: "mr-IN", name: "Marathi",         nativeName: "मराठी",           sttLocale: "mr-IN",  ttsLang: "mr-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "gu-IN", name: "Gujarati",        nativeName: "ગુજરાતી",        sttLocale: "gu-IN",  ttsLang: "gu-IN",  script: "Gujarati",   family: "Indo-Aryan" },
  { code: "pa-IN", name: "Punjabi",         nativeName: "ਪੰਜਾਬੀ",          sttLocale: "pa-IN",  ttsLang: "pa-IN",  script: "Gurmukhi",   family: "Indo-Aryan" },
  { code: "or-IN", name: "Odia",            nativeName: "ଓଡ଼ିଆ",          sttLocale: "or-IN",  ttsLang: "or-IN",  script: "Odia",       family: "Indo-Aryan" },
  { code: "as-IN", name: "Assamese",        nativeName: "অসমীয়া",        sttLocale: "as-IN",  ttsLang: "as-IN",  script: "Bengali",    family: "Indo-Aryan" },
  { code: "ur-IN", name: "Urdu",            nativeName: "اردو",           sttLocale: "ur-IN",  ttsLang: "ur-IN",  script: "Arabic",     family: "Indo-Aryan" },
  { code: "sa-IN", name: "Sanskrit",        nativeName: "संस्कृतम्",        sttLocale: "sa-IN",  ttsLang: "hi-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "mai-IN",name: "Maithili",        nativeName: "मैथिली",          sttLocale: "mai",    ttsLang: "hi-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "sat-IN",name: "Santali",         nativeName: "ᱥᱟᱱᱛᱟᱲᱤ",        sttLocale: "sat",    ttsLang: "hi-IN",  script: "Ol Chiki",   family: "Austroasiatic" },
  { code: "ks-IN", name: "Kashmiri",        nativeName: "کٲشُر",          sttLocale: "ks-IN",  ttsLang: "ur-IN",  script: "Arabic",     family: "Indo-Aryan" },
  { code: "ne-IN", name: "Nepali",          nativeName: "नेपाली",          sttLocale: "ne-IN",  ttsLang: "ne-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "sd-IN", name: "Sindhi",          nativeName: "سنڌي",           sttLocale: "sd-IN",  ttsLang: "sd-IN",  script: "Arabic",     family: "Indo-Aryan" },
  { code: "doi-IN",name: "Dogri",           nativeName: "डोगरी",           sttLocale: "doi",    ttsLang: "hi-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "kok-IN",name: "Konkani",         nativeName: "कोंकणी",          sttLocale: "kok",    ttsLang: "hi-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "mni-IN",name: "Manipuri",        nativeName: "মৈতৈলোন্",        sttLocale: "mni",    ttsLang: "bn-IN",  script: "Meitei",     family: "Sino-Tibetan" },
  { code: "brx-IN",name: "Bodo",            nativeName: "बड़ो",            sttLocale: "brx",    ttsLang: "hi-IN",  script: "Devanagari", family: "Sino-Tibetan" },
  { code: "raj-IN",name: "Rajasthani",      nativeName: "मारवाड़ी",        sttLocale: "hi-IN",  ttsLang: "hi-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "bho-IN",name: "Bhojpuri",        nativeName: "भोजपुरी",          sttLocale: "hi-IN",  ttsLang: "hi-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "hne-IN",name: "Chhattisgarhi",   nativeName: "छत्तीसगढ़ी",       sttLocale: "hi-IN",  ttsLang: "hi-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "bgc-IN",name: "Haryanvi",        nativeName: "हरियाणवी",        sttLocale: "hi-IN",  ttsLang: "hi-IN",  script: "Devanagari", family: "Indo-Aryan" },
  { code: "tcy-IN",name: "Tulu",            nativeName: "ತುಳು",           sttLocale: "kn-IN",  ttsLang: "kn-IN",  script: "Kannada",    family: "Dravidian" },
  { code: "ta-Latn-IN", name: "Tanglish",   nativeName: "Tanglish (தமிழ்)", sttLocale: "en-IN",  ttsLang: "ta-IN",  script: "Latin",      family: "Hybrid" },
  { code: "hi-Latn-IN", name: "Hinglish",   nativeName: "Hinglish (हिन्दी)", sttLocale: "en-IN",  ttsLang: "hi-IN",  script: "Latin",      family: "Hybrid" },
];

// Primary languages with full STT+TTS coverage (Sarvam Saaras/Bulbul level)
export const PRIMARY_LANGUAGES = INDIAN_LANGUAGES.filter(
  (l) => ["en-IN","ta-IN","hi-IN","te-IN","kn-IN","ml-IN","bn-IN","mr-IN","gu-IN","pa-IN","or-IN","ur-IN","ta-Latn-IN","hi-Latn-IN"].includes(l.code)
);

// ─── Voice-flow-style Transcript Cleanup & Legal Grounding ─────────────────
// Removes fillers, handles self-corrections, normalizes statutory terms

const FILLER_PATTERNS = [
  /\b(um+|uh+|ah+|er+|hmm+|hm+|like|you know|basically|actually|so+|well)\b/gi,
  /\b(मतलब|अच्छा|वो|ऐसा|बस|हां|ना|तो)\b/gi,    // Hindi fillers
  /\b(அதாவது|சரி|அப்போ|இல்லை)\b/gi,            // Tamil fillers
  /\b(అంటే|సరే|అప్పుడు)\b/gi,                    // Telugu fillers
  /\b(म्हणजे|बरोबर|मग)\b/gi,                      // Marathi fillers
  /\b(মানে|আচ্ছা|তো)\b/gi,                         // Bengali fillers
];

// Voice Flow context-aware statutory entity normalization
const STATUTORY_TERM_NORMALIZATIONS: Array<[RegExp, string]> = [
  [/\b(irdai|irda)\b/gi, "IRDAI"],
  [/\b(rera)\b/gi, "RERA"],
  [/\b(dgca)\b/gi, "DGCA"],
  [/\b(upi)\b/gi, "UPI"],
  [/\b(tat)\b/gi, "TAT"],
  [/\b(rbi)\b/gi, "RBI"],
  [/\b(ombudsman)\b/gi, "Ombudsman"],
  [/\b(ncdrc)\b/gi, "NCDRC"],
  [/\b(dcdrc)\b/gi, "DCDRC"],
  [/\b(rti)\b/gi, "RTI"],
  [/\brupees\b/gi, "₹"],
  [/\brs\.?\s*(\d+)/gi, "₹$1"],
];

export function cleanTranscript(raw: string): string {
  let cleaned = raw;

  // 1. Handle self-corrections — keep only the corrected part
  cleaned = cleaned.replace(
    /(\w+(?:\s+\w+){0,3}),?\s*(?:no|nah|wait|sorry|I mean|actually)\s+(\w+(?:\s+\w+){0,5})/gi,
    "$2"
  );

  // 2. Remove filler words
  for (const pattern of FILLER_PATTERNS) {
    cleaned = cleaned.replace(pattern, "");
  }

  // 3. Voice Flow statutory entity normalization
  for (const [pattern, replacement] of STATUTORY_TERM_NORMALIZATIONS) {
    cleaned = cleaned.replace(pattern, replacement);
  }

  // 4. Clean up excessive whitespace
  cleaned = cleaned.replace(/\s{2,}/g, " ").trim();

  // 5. Auto-capitalize first letter
  if (cleaned.length > 0) {
    cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  }

  // 6. Ensure ending punctuation
  if (cleaned.length > 0 && !/[.!?।]$/.test(cleaned)) {
    cleaned += ".";
  }

  return cleaned;
}

// ─── Sarvam Saaras-style Language Auto Detection ─────────────────────────

// Unicode block ranges for detecting script
const SCRIPT_DETECTORS: Array<{ scripts: string[]; regex: RegExp; languages: string[] }> = [
  { scripts: ["Devanagari"], regex: /[\u0900-\u097F]/,       languages: ["hi-IN", "mr-IN", "sa-IN"] },
  { scripts: ["Bengali"],    regex: /[\u0980-\u09FF]/,       languages: ["bn-IN", "as-IN"] },
  { scripts: ["Tamil"],      regex: /[\u0B80-\u0BFF]/,       languages: ["ta-IN"] },
  { scripts: ["Telugu"],     regex: /[\u0C00-\u0C7F]/,       languages: ["te-IN"] },
  { scripts: ["Kannada"],    regex: /[\u0C80-\u0CFF]/,       languages: ["kn-IN"] },
  { scripts: ["Malayalam"],  regex: /[\u0D00-\u0D7F]/,       languages: ["ml-IN"] },
  { scripts: ["Gujarati"],   regex: /[\u0A80-\u0AFF]/,       languages: ["gu-IN"] },
  { scripts: ["Gurmukhi"],   regex: /[\u0A00-\u0A7F]/,       languages: ["pa-IN"] },
  { scripts: ["Odia"],       regex: /[\u0B00-\u0B7F]/,       languages: ["or-IN"] },
  { scripts: ["Arabic"],     regex: /[\u0600-\u06FF\uFE70-\uFEFF]/, languages: ["ur-IN", "sd-IN", "ks-IN"] },
  { scripts: ["Ol Chiki"],   regex: /[\u1C50-\u1C7F]/,       languages: ["sat-IN"] },
  { scripts: ["Meitei"],     regex: /[\uABC0-\uABFF]/,       languages: ["mni-IN"] },
];

export function detectLanguageFromText(text: string): VoiceLanguage {
  // Count characters per script
  const scriptCounts = SCRIPT_DETECTORS.map((detector) => ({
    ...detector,
    count: (text.match(detector.regex) || []).length,
  }));

  // Find the dominant script
  const dominant = scriptCounts.reduce((best, current) =>
    current.count > best.count ? current : best
  );

  if (dominant.count > 0) {
    const lang = INDIAN_LANGUAGES.find((l) => dominant.languages.includes(l.code));
    if (lang) return lang;
  }

  // Default: English
  return INDIAN_LANGUAGES[0];
}

// ─── Bolna-style Voice Pipeline Orchestrator ─────────────────────────────

export type VoicePipelineState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "error";

export interface VoicePipelineEvent {
  type: "state_change" | "transcript" | "language_detected" | "response_ready" | "error";
  data: any;
}

type VoicePipelineListener = (event: VoicePipelineEvent) => void;

export class MultilingualVoiceEngine {
  private recognition: any = null;
  private synthesis: SpeechSynthesis | null = null;
  private state: VoicePipelineState = "idle";
  private currentLanguage: VoiceLanguage = INDIAN_LANGUAGES[0]; // Default to English
  private autoDetect = true;
  private continuous = false;
  private interimTranscript = "";
  private finalTranscript = "";
  private listeners: Set<VoicePipelineListener> = new Set();
  private supported = false;
  private ttsVoiceCache: Map<string, SpeechSynthesisVoice | null> = new Map();
  private silenceTimer: number | null = null;

  constructor() {
    if (typeof window === "undefined") return;

    // Initialize STT
    const SpeechRecognition =
      (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.maxAlternatives = 3;
      this.supported = true;
      this.setupRecognitionHandlers();
    }

    // Initialize TTS
    if (window.speechSynthesis) {
      this.synthesis = window.speechSynthesis;
      // Pre-cache voices
      this.cacheVoices();
      window.speechSynthesis.onvoiceschanged = () => this.cacheVoices();
    }
  }

  private cacheVoices() {
    if (!this.synthesis) return;
    const voices = this.synthesis.getVoices();
    for (const lang of INDIAN_LANGUAGES) {
      const exact = voices.find((v) => v.lang === lang.ttsLang);
      const prefix = voices.find((v) => v.lang.startsWith(lang.code.split("-")[0]));
      this.ttsVoiceCache.set(lang.code, exact ?? prefix ?? null);
    }
  }

  private setupRecognitionHandlers() {
    if (!this.recognition) return;

    this.recognition.onresult = (event: any) => {
      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += transcript;
        } else {
          interim += transcript;
        }
      }

      this.interimTranscript = interim;
      if (final) {
        this.finalTranscript += final;
      }

      // Auto-detect language from transcript
      if (this.autoDetect && (final || interim)) {
        const detectedLang = detectLanguageFromText(final || interim);
        if (detectedLang.code !== this.currentLanguage.code) {
          this.currentLanguage = detectedLang;
          this.emit({
            type: "language_detected",
            data: { language: detectedLang, from: "transcript_analysis" },
          });
        }
      }

      this.emit({
        type: "transcript",
        data: {
          interim: this.interimTranscript,
          final: this.finalTranscript,
          cleaned: cleanTranscript(this.finalTranscript),
          raw: (this.finalTranscript + " " + this.interimTranscript).trim(),
        },
      });

      // Reset silence detection timer
      this.resetSilenceTimer();
    };

    this.recognition.onend = () => {
      if (this.state === "listening" && this.continuous) {
        // Auto-restart for continuous mode
        try {
          this.recognition?.start();
        } catch {
          this.setState("idle");
        }
      } else {
        this.setState("idle");
      }
    };

    this.recognition.onerror = (event: any) => {
      if (event.error === "no-speech" || event.error === "aborted") {
        // Not a real error — user stopped speaking or cancelled
        this.setState("idle");
        return;
      }
      this.emit({ type: "error", data: { error: event.error, message: `Speech recognition error: ${event.error}` } });
      this.setState("error");
    };
  }

  private resetSilenceTimer() {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    // Auto-stop after 3s of silence in non-continuous mode
    if (!this.continuous) {
      this.silenceTimer = window.setTimeout(() => {
        if (this.state === "listening" && this.finalTranscript.trim()) {
          this.stopListening();
        }
      }, 3000);
    }
  }

  private setState(state: VoicePipelineState) {
    this.state = state;
    this.emit({ type: "state_change", data: { state } });
  }

  private emit(event: VoicePipelineEvent) {
    this.listeners.forEach((fn) => fn(event));
  }

  // ─── Public API ──────────────────────────────────────────────────────

  get isSupported(): boolean {
    return this.supported;
  }

  get currentState(): VoicePipelineState {
    return this.state;
  }

  get activeLanguage(): VoiceLanguage {
    return this.currentLanguage;
  }

  get availableLanguages(): VoiceLanguage[] {
    return INDIAN_LANGUAGES;
  }

  get primaryLanguages(): VoiceLanguage[] {
    return PRIMARY_LANGUAGES;
  }

  subscribe(listener: VoicePipelineListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  setLanguage(languageCode: string) {
    const lang = INDIAN_LANGUAGES.find((l) => l.code === languageCode);
    if (lang) {
      this.currentLanguage = lang;
      if (this.recognition) {
        this.recognition.lang = lang.sttLocale;
      }
      this.emit({
        type: "language_detected",
        data: { language: lang, from: "manual" },
      });
    }
  }

  setAutoDetect(enabled: boolean) {
    this.autoDetect = enabled;
  }

  setContinuous(enabled: boolean) {
    this.continuous = enabled;
    if (this.recognition) {
      this.recognition.continuous = enabled;
    }
  }

  startListening() {
    if (!this.recognition || this.state === "listening") return;

    this.interimTranscript = "";
    this.finalTranscript = "";
    this.recognition.lang = this.currentLanguage.sttLocale;

    try {
      this.recognition.start();
      this.setState("listening");
    } catch (err) {
      this.emit({ type: "error", data: { error: "start_failed", message: String(err) } });
    }
  }

  stopListening(): string {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    if (this.recognition && this.state === "listening") {
      this.recognition.stop();
    }
    const result = cleanTranscript(this.finalTranscript);
    this.setState("idle");
    return result;
  }

  toggleListening(): boolean {
    if (this.state === "listening") {
      this.stopListening();
      return false;
    } else {
      this.startListening();
      return true;
    }
  }

  // Sarvam Bulbul-style TTS — speak text in the detected/selected language
  speak(text: string, languageCode?: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.synthesis) {
        reject(new Error("Speech synthesis not available"));
        return;
      }

      // Cancel any ongoing speech
      this.synthesis.cancel();

      const lang = languageCode
        ? INDIAN_LANGUAGES.find((l) => l.code === languageCode) ?? this.currentLanguage
        : this.currentLanguage;

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang.ttsLang;
      utterance.rate = 0.95;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;

      // Try to use a cached native voice
      const voice = this.ttsVoiceCache.get(lang.code);
      if (voice) utterance.voice = voice;

      utterance.onstart = () => this.setState("speaking");
      utterance.onend = () => {
        this.setState("idle");
        resolve();
      };
      utterance.onerror = (event) => {
        this.setState("error");
        reject(new Error(`TTS error: ${event.error}`));
      };

      this.synthesis.speak(utterance);
    });
  }

  stopSpeaking() {
    this.synthesis?.cancel();
    this.setState("idle");
  }

  // Get TTS voices available for a language
  getVoicesForLanguage(languageCode: string): SpeechSynthesisVoice[] {
    if (!this.synthesis) return [];
    const lang = INDIAN_LANGUAGES.find((l) => l.code === languageCode);
    if (!lang) return [];
    return this.synthesis
      .getVoices()
      .filter((v) => v.lang.startsWith(lang.code.split("-")[0]));
  }

  destroy() {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    this.stopListening();
    this.stopSpeaking();
    this.listeners.clear();
  }
}

// ─── Singleton Instance ────────────────────────────────────────────────────
let _instance: MultilingualVoiceEngine | null = null;

export function getVoiceEngine(): MultilingualVoiceEngine {
  if (!_instance) {
    _instance = new MultilingualVoiceEngine();
  }
  return _instance;
}
