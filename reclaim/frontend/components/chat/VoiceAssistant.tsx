"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Mic, MicOff, Volume2, VolumeX, Globe, ChevronDown, Loader2,
  Radio, AudioWaveform, Languages, Sparkles, X,
} from "lucide-react";
import {
  getVoiceEngine,
  type VoiceLanguage,
  type VoicePipelineState,
  type VoicePipelineEvent,
  INDIAN_LANGUAGES,
  PRIMARY_LANGUAGES,
} from "@/lib/voice-engine";

// ─── Voice Orb ── Bolna-inspired visual pulse during recording ──────────

function VoiceOrb({ state, size = 56 }: { state: VoicePipelineState; size?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let running = true;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    function draw(t: number) {
      if (!running || !ctx) return;
      ctx.clearRect(0, 0, size, size);

      const cx = size / 2;
      const cy = size / 2;
      const baseR = size * 0.32;

      if (state === "listening") {
        // Pulsing recording orb — 3 concentric rings
        for (let ring = 2; ring >= 0; ring--) {
          const pulseAmp = 3 + ring * 2;
          const phase = t * 0.003 + ring * 1.2;
          const r = baseR + Math.sin(phase) * pulseAmp + ring * 4;
          const alpha = 0.15 - ring * 0.04;
          ctx.beginPath();
          ctx.arc(cx, cy, r, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(220, 38, 38, ${alpha})`;
          ctx.fill();
        }
        // Core pulsing dot
        const pulseR = baseR * 0.55 + Math.sin(t * 0.005) * 3;
        ctx.beginPath();
        ctx.arc(cx, cy, pulseR, 0, Math.PI * 2);
        const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, pulseR);
        gradient.addColorStop(0, "#ef4444");
        gradient.addColorStop(1, "#dc2626");
        ctx.fillStyle = gradient;
        ctx.fill();
      } else if (state === "processing") {
        // Spinning loader
        const angle = t * 0.004;
        ctx.beginPath();
        ctx.arc(cx, cy, baseR * 0.6, angle, angle + Math.PI * 1.5);
        ctx.strokeStyle = "#d97706";
        ctx.lineWidth = 3;
        ctx.lineCap = "round";
        ctx.stroke();
      } else if (state === "speaking") {
        // Audio wave bars
        const barCount = 7;
        const barW = 3;
        const gap = 4;
        const totalW = barCount * barW + (barCount - 1) * gap;
        const startX = cx - totalW / 2;
        for (let i = 0; i < barCount; i++) {
          const phase = t * 0.006 + i * 0.7;
          const h = 8 + Math.abs(Math.sin(phase)) * (baseR * 0.8);
          const x = startX + i * (barW + gap);
          const y = cy - h / 2;
          ctx.fillStyle = "#0284c7";
          ctx.fillRect(x, y, barW, h);
        }
      } else {
        // Idle — static ring (rendered once, no continuous rAF loop)
        ctx.beginPath();
        ctx.arc(cx, cy, baseR * 0.5, 0, Math.PI * 2);
        ctx.strokeStyle = "#a8a29e";
        ctx.lineWidth = 2;
        ctx.stroke();

        // Mic icon stand-in (crosshair)
        ctx.beginPath();
        ctx.moveTo(cx, cy - 6);
        ctx.lineTo(cx, cy + 6);
        ctx.moveTo(cx - 6, cy);
        ctx.lineTo(cx + 6, cy);
        ctx.strokeStyle = "#78716c";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        return;
      }

      animFrameRef.current = requestAnimationFrame(draw);
    }

    animFrameRef.current = requestAnimationFrame(draw);
    return () => {
      running = false;
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [state, size]);


  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      style={{ width: size, height: size }}
      className="pointer-events-none"
    />
  );
}

// ─── Language Selector ── Sarvam-style Language Grid ─────────────────────

function LanguageSelector({
  selectedCode,
  autoDetect,
  onSelect,
  onToggleAutoDetect,
  onClose,
}: {
  selectedCode: string;
  autoDetect: boolean;
  onSelect: (code: string) => void;
  onToggleAutoDetect: () => void;
  onClose: () => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const languages = showAll ? INDIAN_LANGUAGES : PRIMARY_LANGUAGES;

  return (
    <div className="rounded-xl border-2 border-[#231f1d] bg-[#fcfaf5] p-4 shadow-[4px_4px_0_#231f1d] w-full max-w-md">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Globe className="size-4 text-amber-700" />
          <span className="font-mono text-xs font-black uppercase text-stone-800">Voice Language</span>
        </div>
        <button onClick={onClose} className="rounded border border-[#231f1d] p-1 hover:bg-stone-200">
          <X className="size-3" />
        </button>
      </div>

      <button
        onClick={onToggleAutoDetect}
        className={`mb-3 w-full rounded-lg border-2 px-3 py-2 text-left text-xs font-bold transition-all ${
          autoDetect
            ? "border-amber-600 bg-amber-100 text-amber-900 shadow-[2px_2px_0_#231f1d]"
            : "border-stone-300 bg-white text-stone-700 hover:border-[#231f1d]"
        }`}
      >
        <div className="flex items-center gap-2">
          <Languages className="size-3.5" />
          <span>Auto-Detect Language</span>
          {autoDetect && <Sparkles className="size-3 ml-auto text-amber-600" />}
        </div>
        <p className="mt-0.5 text-[10px] font-medium text-stone-500">
          Sarvam Saaras-style auto language detection from speech
        </p>
      </button>

      <div className="grid grid-cols-3 gap-1.5 max-h-64 overflow-y-auto">
        {languages.map((lang) => (
          <button
            key={lang.code}
            onClick={() => onSelect(lang.code)}
            className={`flex flex-col items-start gap-0.5 rounded-lg border px-2.5 py-2 text-left text-[10px] transition-all ${
              selectedCode === lang.code && !autoDetect
                ? "border-amber-600 bg-amber-50 text-amber-900 shadow-[2px_2px_0_#231f1d] font-bold"
                : "border-stone-200 bg-white text-stone-700 hover:border-[#231f1d] hover:bg-stone-50"
            }`}
          >
            <span className="font-bold text-[11px]">{lang.nativeName}</span>
            <span className="text-stone-500">{lang.name}</span>
          </button>
        ))}
      </div>

      <button
        onClick={() => setShowAll(!showAll)}
        className="mt-2 w-full text-center text-[10px] font-bold text-amber-700 hover:text-amber-900"
      >
        {showAll ? "Show Primary Languages" : `Show All ${INDIAN_LANGUAGES.length} Languages`}
      </button>
    </div>
  );
}

// ─── Voice Transcript Display ── Voice-flow-style with cleanup ──────────

function TranscriptDisplay({
  raw,
  cleaned,
  interim,
  detectedLanguage,
}: {
  raw: string;
  cleaned: string;
  interim: string;
  detectedLanguage: VoiceLanguage | null;
}) {
  return (
    <div className="w-full rounded-lg border-2 border-[#231f1d] bg-white p-3 shadow-[2px_2px_0_#231f1d]">
      {/* Live transcript with interim graying */}
      <div className="min-h-[2rem] text-sm font-medium text-stone-900">
        {cleaned || raw ? (
          <>
            <span>{cleaned || raw}</span>
            {interim && (
              <span className="text-stone-400 italic"> {interim}</span>
            )}
          </>
        ) : (
          <span className="text-stone-400">Speak now...</span>
        )}
      </div>

      {/* Language detection badge */}
      {detectedLanguage && (
        <div className="mt-2 flex items-center gap-1.5">
          <span className="rounded border border-[#231f1d] bg-amber-100 px-2 py-0.5 text-[9px] font-mono font-bold uppercase text-amber-900 shadow-[1px_1px_0_#231f1d]">
            {detectedLanguage.nativeName} · {detectedLanguage.name}
          </span>
          <span className="text-[9px] text-stone-500">detected</span>
        </div>
      )}
    </div>
  );
}

// ─── Main Voice Assistant Component ─────────────────────────────────────

interface VoiceAssistantProps {
  onTranscript: (text: string) => void;
  onSpeakResponse?: (text: string) => void;
  compact?: boolean;
}

export function VoiceAssistant({ onTranscript, onSpeakResponse, compact = false }: VoiceAssistantProps) {
  const [mounted, setMounted] = useState(false);
  const engineRef = useRef<any>(null);
  const [state, setState] = useState<VoicePipelineState>("idle");
  const [transcript, setTranscript] = useState({ raw: "", cleaned: "", interim: "" });
  const [detectedLang, setDetectedLang] = useState<VoiceLanguage | null>(null);
  const [selectedLangCode, setSelectedLangCode] = useState("en-IN");
  const [autoDetect, setAutoDetect] = useState(true);
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(true);

  useEffect(() => {
    setMounted(true);
    engineRef.current = getVoiceEngine();
    const engine = engineRef.current;
    const unsubscribe = engine.subscribe((event: VoicePipelineEvent) => {
      switch (event.type) {
        case "state_change":
          setState(event.data.state);
          break;
        case "transcript":
          setTranscript({
            raw: event.data.raw,
            cleaned: event.data.cleaned,
            interim: event.data.interim,
          });
          break;
        case "language_detected":
          setDetectedLang(event.data.language);
          setSelectedLangCode(event.data.language.code);
          break;
        case "error":
          console.warn("Voice engine error:", event.data);
          break;
      }
    });
    return unsubscribe;
  }, []);

  const handleToggle = useCallback(() => {
    if (!engineRef.current) return;
    const engine = engineRef.current;
    if (state === "listening") {
      const result = engine.stopListening();
      if (result.trim()) {
        onTranscript(result);
      }
    } else if (state === "speaking") {
      engine.stopSpeaking();
    } else {
      setTranscript({ raw: "", cleaned: "", interim: "" });
      engine.startListening();
    }
  }, [state, onTranscript]);

  const handleLanguageSelect = useCallback((code: string) => {
    if (!engineRef.current) return;
    setSelectedLangCode(code);
    setAutoDetect(false);
    engineRef.current.setLanguage(code);
    engineRef.current.setAutoDetect(false);
    setLangMenuOpen(false);
  }, []);

  const handleToggleAutoDetect = useCallback(() => {
    if (!engineRef.current) return;
    const newVal = !autoDetect;
    setAutoDetect(newVal);
    engineRef.current.setAutoDetect(newVal);
  }, [autoDetect]);

  const activeLang = INDIAN_LANGUAGES.find((l) => l.code === selectedLangCode) ?? INDIAN_LANGUAGES[0];

  // Prevent SSR/CSR hydration mismatch: render matching static shell before mounting
  if (!mounted) {
    if (compact) {
      return (
        <div className="relative inline-flex items-center gap-1 opacity-75">
          <div className="grid size-9 shrink-0 place-items-center rounded-lg border-2 border-[#231f1d] bg-white text-stone-600 shadow-[2px_2px_0_#231f1d]">
            <Mic className="size-4" />
          </div>
          <div className="rounded border border-[#231f1d] bg-[#fbf9f2] px-1.5 py-0.5 text-[9px] font-mono font-bold text-stone-700 shadow-[1px_1px_0_#231f1d] flex items-center gap-0.5">
            <Globe className="size-2.5" /> AUTO <ChevronDown className="size-2" />
          </div>
        </div>
      );
    }
    return null;
  }

  const isSupported = engineRef.current?.isSupported ?? false;
  if (!isSupported) return null;


  // ─── Compact Mode (inline button for chat composer) ─────────────
  if (compact) {
    return (
      <div className="relative inline-flex items-center gap-1">
        <button
          onClick={handleToggle}
          className={`relative grid size-9 shrink-0 place-items-center rounded-lg border-2 transition-all ${
            state === "listening"
              ? "border-red-500 bg-red-100 text-red-700 shadow-[2px_2px_0_#231f1d] animate-pulse"
              : state === "speaking"
                ? "border-blue-500 bg-blue-100 text-blue-700 shadow-[2px_2px_0_#231f1d]"
                : "border-[#231f1d] bg-white text-stone-700 hover:bg-amber-50 shadow-[2px_2px_0_#231f1d]"
          }`}
          title={
            state === "listening" ? "Stop recording" : state === "speaking" ? "Stop speaking" : "Start voice input"
          }
        >
          {state === "listening" ? (
            <>
              <span className="absolute inset-0 animate-ping rounded-lg bg-red-200/40" />
              <MicOff className="size-4 relative z-10" />
            </>
          ) : state === "speaking" ? (
            <VolumeX className="size-4" />
          ) : (
            <Mic className="size-4" />
          )}
        </button>

        {/* Language badge */}
        <button
          onClick={() => setLangMenuOpen(!langMenuOpen)}
          className="rounded border border-[#231f1d] bg-[#fbf9f2] px-1.5 py-0.5 text-[9px] font-mono font-bold text-stone-700 hover:bg-amber-50 shadow-[1px_1px_0_#231f1d] flex items-center gap-0.5"
          title="Change voice language"
        >
          <Globe className="size-2.5" />
          {autoDetect ? "AUTO" : activeLang.name.slice(0, 3).toUpperCase()}
          <ChevronDown className="size-2" />
        </button>

        {/* Dropdown language selector */}
        {langMenuOpen && (
          <div className="absolute bottom-full right-0 z-50 mb-2">
            <LanguageSelector
              selectedCode={selectedLangCode}
              autoDetect={autoDetect}
              onSelect={handleLanguageSelect}
              onToggleAutoDetect={handleToggleAutoDetect}
              onClose={() => setLangMenuOpen(false)}
            />
          </div>
        )}
      </div>
    );
  }

  // ─── Full Mode (standalone voice panel) ────────────────────────
  return (
    <div className="flex flex-col items-center gap-4 rounded-xl border-2 border-[#231f1d] bg-[#fcfaf5] p-6 shadow-[4px_4px_0_#231f1d]">
      {/* Language selector bar */}
      <div className="w-full flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio className="size-3.5 text-amber-700" />
          <span className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-700">
            [ ◈ VOICE ENGINE ]
          </span>
        </div>
        <button
          onClick={() => setLangMenuOpen(!langMenuOpen)}
          className="pixel-btn text-[10px] px-2 py-1 flex items-center gap-1"
        >
          <Globe className="size-3" />
          {autoDetect ? "Auto-Detect" : activeLang.nativeName}
          <ChevronDown className="size-2.5" />
        </button>
      </div>

      {langMenuOpen && (
        <LanguageSelector
          selectedCode={selectedLangCode}
          autoDetect={autoDetect}
          onSelect={handleLanguageSelect}
          onToggleAutoDetect={handleToggleAutoDetect}
          onClose={() => setLangMenuOpen(false)}
        />
      )}

      {/* Voice Orb */}
      <button
        onClick={handleToggle}
        className="group relative flex flex-col items-center gap-3 focus:outline-none"
        aria-label={state === "listening" ? "Stop recording" : "Start voice input"}
      >
        <div className={`rounded-full border-2 p-2 transition-all ${
          state === "listening"
            ? "border-red-400 bg-red-50 shadow-[3px_3px_0_#dc2626]"
            : state === "speaking"
              ? "border-blue-400 bg-blue-50 shadow-[3px_3px_0_#0284c7]"
              : "border-[#231f1d] bg-white shadow-[3px_3px_0_#231f1d] group-hover:bg-amber-50"
        }`}>
          <VoiceOrb state={state} size={72} />
        </div>
        <span className="text-xs font-bold text-stone-700">
          {state === "listening"
            ? "Listening... Tap to stop"
            : state === "processing"
              ? "Processing..."
              : state === "speaking"
                ? "Speaking... Tap to stop"
                : "Tap to speak"}
        </span>
      </button>

      {/* Transcript */}
      {(transcript.raw || transcript.interim || state === "listening") && (
        <TranscriptDisplay
          raw={transcript.raw}
          cleaned={transcript.cleaned}
          interim={transcript.interim}
          detectedLanguage={detectedLang}
        />
      )}

      {/* Model credits */}
      <div className="w-full flex flex-wrap items-center justify-center gap-1 pt-2 border-t border-stone-200">
        <span className="text-[9px] text-stone-400 font-mono">Powered by:</span>
        {["Sarvam Saaras", "Bulbul TTS", "Voice Canto", "Bolna Pipeline"].map((name) => (
          <span key={name} className="rounded border border-stone-300 bg-white px-1.5 py-0.5 text-[8px] font-mono font-bold text-stone-500 shadow-[1px_1px_0_#d6d3d1]">
            {name}
          </span>
        ))}
      </div>
    </div>
  );
}
