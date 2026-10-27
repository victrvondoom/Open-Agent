"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot, Send, Sparkles, Loader2, AlertCircle, Command, Trash2, RotateCcw, Zap, Volume2,
} from "lucide-react";
import {
  classifyQuery, runMultiDomainCase, type DomainCandidate, type Citation, type MultiDomainCaseResponse, type AgentBreakdown,
} from "@/lib/api-client";
import { ESTIMATED_STAGES } from "./pipeline";
import { ReasoningLanes } from "./ReasoningLanes";
import { CitationConstellation } from "./CitationConstellation";
import { domainTheme } from "./domain-theme";
import { markdownComponents } from "./markdown-components";
import { AgentReasoningTrace } from "./AgentReasoningTrace";
import { PipelineSidebar } from "./PipelineSidebar";
import { VoiceAssistant } from "./VoiceAssistant";
import { getVoiceEngine } from "@/lib/voice-engine";
import { SYNTHETIC_SCENARIOS } from "@/lib/synthetic-scenarios";

interface DomainAnswer {
  domain: string;
  route: string;
  report: string | null;
  trace: string[];
  breakdown: AgentBreakdown;
  confidence: number;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  domains?: string[];
  citations?: Citation[];
  perDomainTraces?: Record<string, string[]>;
  perDomainAnswers?: DomainAnswer[];
  error?: string;
}

// Bumped to v2 when DomainAnswer gained required trace/breakdown/confidence
// fields -- old v1 history in a returning user's browser predates those
// fields entirely (not just empty), so loading it would crash components
// that read them. A new key just leaves the old entry orphaned in
// localStorage rather than needing a migration.
const STORAGE_KEY = "proxy:assistant-chat-history-v2";

function loadHistory(): ChatMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(messages: ChatMessage[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-50)));
  } catch {
    // storage full or unavailable -- conversation still works, just won't persist
  }
}

// Old useSpeechRecognition hook removed — replaced by
// MultilingualVoiceEngine (lib/voice-engine.ts) which supports
// 22+ Indian languages via Sarvam Saaras / Bolna / Voice Flow architecture.

export function AssistantChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [livePreview, setLivePreview] = useState<DomainCandidate[]>([]);
  const [processing, setProcessing] = useState(false);
  const [processingDomains, setProcessingDomains] = useState<string[]>([]);
  const [filledCount, setFilledCount] = useState(0);
  const [processingElapsedMs, setProcessingElapsedMs] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stageTimerRef = useRef<number | null>(null);

  // ESTIMATED_STAGES finishes animating in ~10s, but a real multi-agent run
  // (several sequential LLM calls per domain) can take 30-120+s -- without a
  // ticking clock the UI looks frozen for the rest of that time.
  useEffect(() => {
    if (!processing) {
      setProcessingElapsedMs(0);
      return;
    }
    const start = performance.now();
    const timer = window.setInterval(() => setProcessingElapsedMs(Math.round(performance.now() - start)), 200);
    return () => window.clearInterval(timer);
  }, [processing]);

  useEffect(() => setMessages(loadHistory()), []);
  useEffect(() => { if (messages.length) saveHistory(messages); }, [messages]);

  // Cross-page handoff from Cross-Domain Search's "Ask the AI Assistant"
  // action (?q=...) -- pre-fills but doesn't auto-send, so the user reviews
  // before it runs a real (slow, LLM-backed) multi-agent query.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    if (q) {
      setInput(q);
      window.setTimeout(() => textareaRef.current?.focus(), 100);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, filledCount]);

  useEffect(() => {
    if (input.trim().length < 12) {
      setLivePreview([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        setLivePreview((await classifyQuery(input)).candidates);
      } catch {
        setLivePreview([]);
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    function onKeydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        textareaRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, []);

  // Multilingual voice input handler — uses the new VoiceAssistant
  const handleVoiceTranscript = useCallback((text: string) => {
    setInput((current) => (current ? `${current} ${text}` : text));
  }, []);

  async function send() {
    const text = input.trim();
    if (!text || processing) return;

    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: text, timestamp: Date.now() }]);
    const caseId = crypto.randomUUID();
    setInput("");
    setLivePreview([]);
    setProcessing(true);
    setFilledCount(0);
    setProcessingDomains(livePreview.length ? livePreview.map((c) => c.domain) : []);

    let stageIndex = 0;
    stageTimerRef.current = window.setInterval(() => {
      stageIndex = Math.min(stageIndex + 1, ESTIMATED_STAGES.length);
      setFilledCount(stageIndex);
    }, 1300);

    try {
      const response: MultiDomainCaseResponse = await runMultiDomainCase(caseId, text);
      const perDomainTraces: Record<string, string[]> = {};
      const perDomainAnswers: DomainAnswer[] = [];
      Object.entries(response.per_domain_results).forEach(([domain, result]) => {
        perDomainTraces[domain] = result.agent_trace ?? [];
        perDomainAnswers.push({ domain, route: result.route, report: result.final_report, trace: result.agent_trace ?? [], breakdown: result.agent_breakdown, confidence: result.confidence });
      });
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "",
          timestamp: Date.now(),
          domains: response.domains_analyzed,
          citations: response.combined_citations,
          perDomainTraces,
          perDomainAnswers,
        },
      ]);
    } catch (err) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "",
          timestamp: Date.now(),
          error: err instanceof Error ? err.message : "Something went wrong reaching the multi-agent backend.",
        },
      ]);
    } finally {
      if (stageTimerRef.current) window.clearInterval(stageTimerRef.current);
      setProcessing(false);
      setProcessingDomains([]);
      setFilledCount(0);
    }
  }

  function retryLast() {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    setMessages((current) => (current[current.length - 1]?.role === "assistant" ? current.slice(0, -1) : current));
    setInput(lastUser.content);
    window.setTimeout(() => send(), 0);
  }

  function clearConversation() {
    setMessages([]);
    window.localStorage.removeItem(STORAGE_KEY);
  }

  // The sidebar always reflects the most current turn: while typing/running
  // it's the live classification + in-flight trace; once a message lands,
  // it switches to that message's real first-domain trace and breakdown.
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant" && !m.error);
  const primaryAnswer = lastAssistant?.perDomainAnswers?.[0];
  const sidebarCandidates = processing
    ? (processingDomains.length ? processingDomains : livePreview.map((c) => c.domain)).map((d) => ({ domain: d }))
    : livePreview.length > 0
      ? livePreview.map((c) => ({ domain: c.domain, confidence: c.confidence }))
      : (lastAssistant?.domains ?? []).map((d) => ({
          domain: d,
          confidence: lastAssistant?.perDomainAnswers?.find((a) => a.domain === d)?.confidence,
        }));
  const sidebarTrace = processing ? [] : primaryAnswer?.trace ?? [];

  return (
    <div className="flex min-h-0 flex-1 gap-4">
      <div className="flex min-h-0 flex-1 flex-col rounded-xl border-2 border-[#231f1d] bg-white shadow-[4px_4px_0_#231f1d]">
        <ChatHeader onClear={clearConversation} busy={processing} />

        {/* This is the only scrollable region -- the header above and the
            Composer below are outside this div, in the same flex-col, so
            they hold a fixed position regardless of how much content
            streams in here. min-h-0 is required: without it a flex child
            refuses to shrink below its content size, and overflow-y-auto
            never actually kicks in, letting this div (and the whole page)
            grow taller with every generated answer instead. */}
        <div ref={scrollRef} className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-6 sm:px-8">
          {messages.length === 0 && !processing && <BootSequence onPick={setInput} />}

          {messages.map((message) =>
            message.role === "user" ? (
              <UserPrompt key={message.id} text={message.content} />
            ) : (
              <IntelligenceCard key={message.id} message={message} onRetry={message.error ? retryLast : undefined} />
            )
          )}

          {processing && (
            <IntelligenceCard
              message={{ id: "processing", role: "assistant", content: "", timestamp: Date.now() }}
              processing
              processingDomains={processingDomains.length ? processingDomains : ["health_insurance"]}
              filledCount={filledCount}
              elapsedMs={processingElapsedMs}
            />
          )}
        </div>

        <Composer
          input={input}
          setInput={setInput}
          onSend={send}
          processing={processing}
          textareaRef={textareaRef}
          onVoiceTranscript={handleVoiceTranscript}
          livePreview={livePreview}
        />
      </div>

      {/* No overflow-y-auto here: the sidebar's natural content height
          (Detected + Agent Pipeline) comfortably fits without scrolling in
          normal use, and forcing it into the row's clamped height with
          scrollbars now hidden globally meant content got silently clipped
          with no visible affordance that more existed below. */}
      <div className="hidden self-start py-4 xl:block">
        <PipelineSidebar
          candidates={sidebarCandidates}
          primaryDomain={primaryAnswer?.domain}
          primaryRoute={primaryAnswer?.route}
          trace={sidebarTrace}
          processing={processing}
        />
      </div>
    </div>
  );
}

function ChatHeader({ onClear, busy }: { onClear: () => void; busy: boolean }) {
  return (
    <div className="flex items-center justify-between border-b-2 border-stone-200 px-4 py-3 sm:px-6 bg-[#fcfaf5] rounded-t-xl">
      <div className="flex items-center gap-3">
        <div className="relative grid size-9 place-items-center rounded-lg border-2 border-[#231f1d] bg-amber-200 shadow-[2px_2px_0_#231f1d]">
          <Sparkles className="size-4 text-stone-900" />
          {busy && <span className="absolute -right-1 -top-1 size-2.5 animate-ping rounded-full bg-amber-500" />}
          {busy && <span className="absolute -right-1 -top-1 size-2.5 rounded-full bg-amber-500 border border-[#231f1d]" />}
        </div>
        <div>
          <p className="text-sm font-black text-[#1c1917] font-mono uppercase">RESOLVE Neural Assistant</p>
          <p className="text-[11px] font-medium text-stone-600">8 domains &middot; {INDIAN_LANGUAGES.length} languages &middot; multi-agent reasoning</p>
        </div>
      </div>
      <button
        onClick={onClear}
        className="pixel-btn text-xs px-2.5 py-1.5 inline-flex items-center gap-1.5 text-stone-700 hover:bg-red-50 hover:text-red-700"
      >
        <Trash2 className="size-3.5" /> Clear
      </button>
    </div>
  );
}

function BootSequence({ onPick }: { onPick: (prompt: string) => void }) {
  const lines = [
    "Domain Router: 8 domains online",
    `Voice Engine: ${INDIAN_LANGUAGES.length} languages active`,
    "Evidence Scoring Engine: ready",
    "Citation Engine: ready",
    "Multi-agent workflow: ready to reason",
  ];
  const suggestions = [
    "My flight was cancelled and my travel insurance rejected the claim.",
    "What documents do I need to dispute a duplicate UPI charge?",
    "My builder delayed possession of my flat by 18 months under RERA.",
    "What are the symptoms of dengue fever and when should I see a doctor?",
    "My credit card was charged twice for the same transaction.",
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center gap-8 py-10">
      <div className="text-center">
        <div className="mx-auto mb-4 grid size-16 place-items-center rounded-xl border-2 border-[#231f1d] bg-amber-200 shadow-[3px_3px_0_#231f1d]">
          <Bot className="size-8 text-stone-900" />
        </div>
        <div className="font-mono text-[11px] text-stone-500">
          {lines.map((line, index) => (
            <p
              key={line}
              className="opacity-0"
              style={{ animation: `fadeIn .4s ease forwards`, animationDelay: `${index * 220}ms` }}
            >
              <span className="text-emerald-600">&#10003;</span> {line}
            </p>
          ))}
        </div>
        <p className="mt-4 text-lg font-black text-[#1c1917] font-mono uppercase">Ask in Any Indian Language</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-stone-600 font-medium">
          One question can span multiple domains. Speak or type in {INDIAN_LANGUAGES.length} languages. Watch RESOLVE classify, reason, and cite.
        </p>
      </div>
      <div className="grid w-full max-w-lg gap-2 sm:grid-cols-2">
        {suggestions.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onPick(prompt)}
            className="rounded-lg border-2 border-stone-300 bg-white p-3 text-left text-xs text-stone-700 font-medium transition-all hover:border-[#231f1d] hover:bg-amber-50 hover:shadow-[2px_2px_0_#231f1d]"
          >
            {prompt}
          </button>
        ))}
      </div>
      <div className="w-full max-w-4xl">
        <p className="mb-2 text-center font-mono text-[11px] font-bold uppercase tracking-widest text-stone-500">
          Story scenarios &middot; pick one to see the full workflow
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          {SYNTHETIC_SCENARIOS.map((scenario) => (
            <div key={scenario.domain} className="rounded-lg border-2 border-[#231f1d] bg-white p-3 text-left shadow-[3px_3px_0_#231f1d]">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-sm font-black text-stone-900">{scenario.title}</span>
                <span className="rounded border border-stone-300 bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase text-stone-700">
                  {domainTheme(scenario.domain).label}
                </span>
              </div>
              <ol className="mb-2 space-y-1 border-l-2 border-amber-300 pl-3 text-[11px] text-stone-600">
                {scenario.story.map((step, i) => (
                  <li key={step}><span className="font-mono font-bold text-amber-700">{i + 1}.</span> {step}</li>
                ))}
              </ol>
              <button
                onClick={() => onPick(scenario.prompt)}
                className="rounded border-2 border-[#231f1d] bg-amber-300 px-2 py-1 text-[11px] font-bold text-stone-900 hover:bg-amber-200"
              >
                Try this scenario
              </button>
            </div>
          ))}
        </div>
      </div>
      <style jsx>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(2px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

function UserPrompt({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[70%] rounded-xl rounded-tr-sm border-2 border-[#231f1d] bg-amber-50 px-4 py-2.5 text-sm font-medium text-[#1c1917] shadow-[2px_2px_0_#231f1d]">
        {text}
      </div>
    </div>
  );
}

const STILL_REASONING_PHRASES = [
  "Reasoning across domains...",
  "Cross-checking clauses and regulations...",
  "Scoring evidence and building strategy...",
  "Complex multi-domain queries can take up to two minutes -- still working.",
];

function IntelligenceCard({
  message, processing, processingDomains, filledCount, elapsedMs, onRetry,
}: {
  message: ChatMessage;
  processing?: boolean;
  processingDomains?: string[];
  filledCount?: number;
  elapsedMs?: number;
  onRetry?: () => void;
}) {
  const domains = processing ? (processingDomains ?? []) : message.domains ?? [];
  const lanes = domains.map((domain) => ({ domain, trace: message.perDomainTraces?.[domain] }));
  const elapsedSeconds = (elapsedMs ?? 0) / 1000;
  const reasoningLabel = STILL_REASONING_PHRASES[Math.min(Math.floor(elapsedSeconds / 15), STILL_REASONING_PHRASES.length - 1)];

  return (
    <div className="rounded-xl border-2 border-[#231f1d] bg-[#fcfaf5] p-4 sm:p-5 shadow-[2px_2px_0_#231f1d]">
      <div className="mb-3 flex items-center gap-2">
        <div className="grid size-7 place-items-center rounded-lg border border-cyan-300/25 bg-cyan-300/10">
          {processing ? <Loader2 className="size-3.5 animate-spin text-cyan-200" /> : <Zap className="size-3.5 text-cyan-200" />}
        </div>
        <p className="text-xs font-medium text-proxy-muted">
          {processing ? reasoningLabel : "RESOLVE"}
        </p>
        {processing && (
          <span className="ml-auto font-mono text-[10px] text-cyan-200">{elapsedSeconds.toFixed(1)}s</span>
        )}
        {!processing && domains.length > 0 && (
          <div className="ml-auto flex flex-wrap gap-1.5">
            {domains.map((domain) => {
              const theme = domainTheme(domain);
              return (
                <span
                  key={domain}
                  className="rounded-full border px-2 py-0.5 text-[10px]"
                  style={{ borderColor: `${theme.color}40`, backgroundColor: `${theme.color}1a`, color: theme.color }}
                >
                  {theme.label}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {lanes.length > 0 && (
        <div className="mb-4">
          <ReasoningLanes lanes={lanes} processing={Boolean(processing)} filledCount={filledCount ?? lanes[0]?.trace?.length ?? 0} />
        </div>
      )}

      {message.error ? (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-red-300/25 bg-red-300/10 px-4 py-3 text-sm text-red-100">
          <span className="flex items-center gap-2"><AlertCircle className="size-4 shrink-0" /> {message.error}</span>
          {onRetry && (
            <button onClick={onRetry} className="inline-flex shrink-0 items-center gap-1 text-xs text-red-200 hover:text-red-100">
              <RotateCcw className="size-3" /> Retry
            </button>
          )}
        </div>
      ) : (
        message.perDomainAnswers && (
          <div className="space-y-3">
            {message.perDomainAnswers.map((answer) => (
              <DomainAnswerSection key={answer.domain} answer={answer} />
            ))}
          </div>
        )
      )}

      {message.citations && message.citations.length > 0 && (
        <div className="mt-4 border-t border-white/5 pt-4">
          <CitationConstellation citations={message.citations} />
        </div>
      )}
    </div>
  );
}

function DomainAnswerSection({ answer }: { answer: DomainAnswer }) {
  const theme = domainTheme(answer.domain);
  const [expanded, setExpanded] = useState(true);
  const [speaking, setSpeaking] = useState(false);
  if (!answer.report) return null;

  async function handleToggleSpeech(e: React.MouseEvent) {
    e.stopPropagation();
    const engine = getVoiceEngine();
    if (speaking) {
      engine.stopSpeaking();
      setSpeaking(false);
    } else {
      setSpeaking(true);
      try {
        // Strip markdown formatting for cleaner speech synthesis
        const plainText = (answer.report || "")
          .replace(/[#*`_\[\]()]/g, " ")
          .replace(/\s+/g, " ")
          .trim();
        await engine.speak(plainText);
      } catch (err) {
        console.warn("TTS playback failed:", err);
      } finally {
        setSpeaking(false);
      }
    }
  }

  return (
    <div className="overflow-hidden rounded-xl border-2 border-[#231f1d] bg-white shadow-[2.5px_2.5px_0_#231f1d]" style={{ borderLeftColor: theme.color, borderLeftWidth: 4 }}>
      <button
        onClick={() => setExpanded((current) => !current)}
        className="flex w-full items-center justify-between bg-[#fbf9f2] border-b-2 border-stone-200 px-3.5 py-2 text-left"
      >
        <span className="flex items-center gap-2 text-xs font-bold text-stone-900">
          <span className="size-2 rounded-full" style={{ backgroundColor: theme.color }} />
          {theme.label}
          <span className="rounded border border-[#231f1d] bg-white px-1.5 py-0.5 text-[10px] font-mono text-stone-800 shadow-[1px_1px_0_#231f1d]">{answer.route}</span>
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={handleToggleSpeech}
            className={`inline-flex items-center gap-1 rounded border border-[#231f1d] px-2 py-0.5 text-[10px] font-bold shadow-[1px_1px_0_#231f1d] transition-all ${
              speaking ? "bg-amber-300 text-stone-900 animate-pulse" : "bg-white text-stone-700 hover:bg-amber-50"
            }`}
            title={speaking ? "Stop voice playback" : "Listen to legal advice"}
          >
            <Volume2 className="size-3 text-stone-800" />
            <span>{speaking ? "Stop Audio" : "Listen (Voice)"}</span>
          </button>
          <span className="font-mono text-[10px] text-stone-500">{expanded ? "Collapse" : "Expand"}</span>
        </div>
      </button>
      {expanded && (
        <div className="px-4 py-3 bg-white">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {answer.report}
          </ReactMarkdown>
          <DraftedDocuments negotiation={answer.breakdown.negotiation} color={theme.color} />
          <AgentReasoningTrace trace={answer.trace} breakdown={answer.breakdown} />
        </div>
      )}
    </div>
  );
}

// The negotiation agent already drafts these on every run -- the
// synthesized report now points to them ("the appeal letter is drafted
// below") instead of asking "would you like me to draft this?", since this
// chat has no conversation continuity between messages. That reference is
// only true if they're actually rendered somewhere, which they previously
// weren't: the agent trace above only ever showed step badges, never the
// document text itself.
function DraftedDocuments({ negotiation, color }: { negotiation?: AgentBreakdown["negotiation"]; color: string }) {
  if (!negotiation) return null;
  const docs: Array<[string, string | undefined]> = [
    ["Appeal / dispute letter", negotiation.appeal_letter],
    ["Complaint email", negotiation.complaint_email],
    ["Escalation note", negotiation.escalation_note],
    ["Consumer complaint", negotiation.consumer_complaint],
  ];
  const available = docs.filter(([, v]) => v && v.trim()) as Array<[string, string]>;
  if (available.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      <p className="text-[10px] font-mono font-bold uppercase tracking-wide text-stone-600">Drafted documents (ready to review and send)</p>
      {available.map(([label, content]) => (
        <details key={label} className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-2.5 shadow-[2px_2px_0_#231f1d]">
          <summary className="cursor-pointer text-xs font-bold text-stone-900">{label}</summary>
          <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-stone-800 font-sans">{content}</p>
        </details>
      ))}
    </div>
  );
}

function Composer({
  input, setInput, onSend, processing, textareaRef, onVoiceTranscript, livePreview,
}: {
  input: string;
  setInput: (value: string) => void;
  onSend: () => void;
  processing: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onVoiceTranscript: (text: string) => void;
  livePreview: DomainCandidate[];
}) {
  return (
    <div className="border-t-2 border-stone-200 p-3 sm:p-4 bg-[#fbf9f2]">
      {livePreview.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5 px-1">
          <span className="text-[10px] font-mono font-bold uppercase tracking-wide text-stone-500">Detected:</span>
          {livePreview.map((candidate) => {
            const theme = domainTheme(candidate.domain);
            return (
              <span
                key={candidate.domain}
                className="rounded border border-[#231f1d] px-2 py-0.5 text-[10px] font-mono font-bold bg-white text-stone-900 shadow-[1px_1px_0_#231f1d]"
              >
                {theme.label} ({Math.round(candidate.confidence * 100)}%)
              </span>
            );
          })}
        </div>
      )}
      <div className="flex items-end gap-2 rounded-xl border-2 border-[#231f1d] bg-white p-2 shadow-[3px_3px_0_#231f1d]">
        <Zap className="mt-2 ml-1 size-4 shrink-0 text-amber-600" />
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
          placeholder="Describe your dispute in any Indian language — voice or text... (Ctrl/Cmd+K to focus)"
          rows={1}
          className="max-h-32 flex-1 resize-none bg-transparent px-2 py-2 text-sm font-medium text-[#1c1917] outline-none placeholder:text-stone-500"
        />

        {/* Multilingual Voice Input — 22+ Indian languages */}
        <VoiceAssistant onTranscript={onVoiceTranscript} compact />

        <button
          onClick={onSend}
          disabled={processing || !input.trim()}
          className="pixel-btn-primary grid size-10 shrink-0 place-items-center disabled:opacity-40 disabled:cursor-not-allowed"
          title="Analyze Claim"
        >
          {processing ? <Loader2 className="size-4 animate-spin text-stone-900" /> : <Send className="size-4 text-stone-900" />}
        </button>
      </div>
      <div className="mt-1.5 flex items-center gap-1 px-1 text-[10px] text-stone-500">
        <Command className="size-3" /> K to focus · Enter to send · Shift+Enter for new line · 🗣 {INDIAN_LANGUAGES.length} languages supported
      </div>
    </div>
  );
}

// Re-export for Composer's language count badge
import { INDIAN_LANGUAGES } from "@/lib/voice-engine";
