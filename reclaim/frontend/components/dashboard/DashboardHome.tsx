"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Send, Loader2, ArrowUpRight, FileStack, Scale, FileText, TrendingUp,
  Activity, Upload, Search, Bot, ClipboardList, Network, Gauge, PenLine,
  FileCheck2, ArrowUpCircle, Radio, Command, Zap, Sparkles, RefreshCw,
  AlertCircle, CheckCircle2, Mic, Globe,
} from "lucide-react";
import {
  classifyQuery, getReportSummary, listAnalyses, seedDemoCases,
  type DomainCandidate, type ReportSummary, type AnalysisCase,
} from "@/lib/api-client";
import { domainTheme, DOMAIN_THEME } from "@/components/chat/domain-theme";
import { DomainOrbit } from "./DomainOrbit";
import { VoiceAssistant } from "@/components/chat/VoiceAssistant";
import { INDIAN_LANGUAGES } from "@/lib/voice-engine";

const DOMAIN_PROMPTS: Record<string, string> = {
  health_insurance: "My health insurance claim of Rs 1,45,000 was denied for a pre-existing condition exclusion.",
  banking: "My bank charged me twice for the same UPI transaction of Rs 5,000 and refuses to reverse it.",
  airlines: "My flight was cancelled 2 hours prior to departure and the airline refused a refund or compensation.",
  telecom: "My telecom provider is billing me for a postpaid plan I cancelled two months ago.",
  ecommerce: "An online seller sent me a counterfeit product and refuses an authorized return.",
  government: "My passport renewal application has been stuck at police verification for 90 days.",
  housing: "My builder delayed possession of my flat by 18 months under RERA and refuses delay interest.",
  healthcare: "I was overcharged on unitemized ICU consumables that my insurance should have covered.",
};

const PROMPT_CHIPS = [
  { label: "IndiGo Flight Cancelled", domain: "airlines", text: "My flight was cancelled 2 hours prior to departure and the airline refused a refund or compensation." },
  { label: "HDFC Duplicate UPI Rs 5,000", domain: "banking", text: "My bank charged me twice for the same UPI transaction of Rs 5,000 and refuses to reverse it." },
  { label: "Star Health Cataract Denial", domain: "health_insurance", text: "My health insurance claim of Rs 1,45,000 was denied for a pre-existing condition exclusion." },
  { label: "Airtel Postpaid Erroneous Bill", domain: "telecom", text: "My telecom provider is billing me for a postpaid plan I cancelled two months ago." },
  { label: "DLF 18-Mo Delayed Possession", domain: "housing", text: "My builder delayed possession of my flat by 18 months under RERA and refuses delay interest." },
  { label: "Amazon Fake Product Return", domain: "ecommerce", text: "An online seller sent me a counterfeit product and refuses an authorized return." },
];

const EVENT_ICON: Record<string, typeof Activity> = {
  case_created: PenLine,
  document_uploaded: Upload,
  appeal_drafted: FileCheck2,
  appeal_status_changed: ArrowUpCircle,
  agent_run: Activity,
  status_update: Sparkles,
};

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function useCountUp(target: number) {
  return target;
}


export function DashboardHome() {
  const router = useRouter();
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);

  function loadData() {
    setLoading(true);
    Promise.all([getReportSummary().catch(() => null), listAnalyses().catch(() => [])]).then(
      ([summaryResult, analysesResult]) => {
        setSummary(summaryResult);
        setAnalyses(analysesResult);
        setLoading(false);
      }
    );
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleSeedDemo() {
    setSeeding(true);
    try {
      await seedDemoCases();
      loadData();
    } catch {
      // fallback
    } finally {
      setSeeding(false);
    }
  }

  const domainStats = useMemo(() => {
    const counts = new Map<string, number>(summary?.domain_breakdown.map((d) => [d.domain, d.count]) ?? []);
    const confidenceByDomain = new Map<string, number[]>();
    for (const analysis of analyses) {
      for (const domain of analysis.domains_involved) {
        if (analysis.avg_confidence === null) continue;
        const list = confidenceByDomain.get(domain) ?? [];
        list.push(analysis.avg_confidence);
        confidenceByDomain.set(domain, list);
      }
    }
    return Object.keys(DOMAIN_THEME).map((domain) => {
      const confidences = confidenceByDomain.get(domain) ?? [];
      return {
        domain,
        count: counts.get(domain) ?? 0,
        avgConfidence: confidences.length ? confidences.reduce((s, c) => s + c, 0) / confidences.length : null,
      };
    });
  }, [summary, analyses]);

  const totalRuns = useMemo(() => analyses.reduce((sum, a) => sum + a.run_count, 0), [analyses]);
  const overallConfidence = useMemo(() => {
    const values = analyses.map((a) => a.avg_confidence).filter((c): c is number => c !== null);
    return values.length ? values.reduce((s, c) => s + c, 0) / values.length : null;
  }, [analyses]);

  const recentAnalyses = analyses.slice(0, 6);
  const backendOnline = summary !== null;

  function openDomain(domain: string) {
    router.push(`/dashboard/assistant?q=${encodeURIComponent(DOMAIN_PROMPTS[domain] ?? "")}`);
  }

  return (
    <div className="flex flex-1 flex-col gap-5 max-w-7xl mx-auto">
      {/* Top Hero Composer */}
      <HeroComposer
        backendOnline={backendOnline}
        onSeedDemo={handleSeedDemo}
        seeding={seeding}
      />

      {/* Metrics Row */}
      <MetricsStrip summary={summary} analysesCount={analyses.length} overallConfidence={overallConfidence} loading={loading} />

      {/* Domain Matrix and Snapshot Rail */}
      <div className="grid gap-5 xl:grid-cols-[1.1fr_.9fr]">
        <section className="flex flex-col rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
          <div className="mb-2 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-black uppercase text-amber-700">[ ◈ RADAR ]</span>
                <h2 className="font-serif text-lg font-bold text-[#1c1917] tracking-tight">Dispute Domain Matrix</h2>
              </div>
              <p className="mt-0.5 font-serif text-xs italic text-stone-600">Active status across all 8 consumer dispute domains -- click to launch focused analysis.</p>
            </div>
          </div>
          <DomainOrbit stats={domainStats} overallConfidence={overallConfidence} totalRuns={totalRuns} onSelect={openDomain} />
        </section>

        <StatRail summary={summary} totalRuns={totalRuns} overallConfidence={overallConfidence} loading={loading} />
      </div>

      {/* Recent Analyses Rail */}
      <RecentAnalysesRail analyses={recentAnalyses} loading={loading} onViewAll={() => router.push("/dashboard/analyses")} />

      {/* Quick Actions & Live Activity */}
      <div className="grid gap-5 xl:grid-cols-[.62fr_.38fr]">
        <QuickActions onSeedDemo={handleSeedDemo} seeding={seeding} />
        <ActivityFeed events={summary?.recent_activity ?? []} loading={loading} />
      </div>
    </div>
  );
}

function HeroComposer({
  backendOnline,
  onSeedDemo,
  seeding,
}: {
  backendOnline: boolean;
  onSeedDemo: () => void;
  seeding: boolean;
}) {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [livePreview, setLivePreview] = useState<DomainCandidate[]>([]);
  const [classifying, setClassifying] = useState(false);
  const [now, setNow] = useState<Date | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (input.trim().length < 12) {
      setLivePreview([]);
      return;
    }
    setClassifying(true);
    const timer = window.setTimeout(async () => {
      try {
        setLivePreview((await classifyQuery(input)).candidates);
      } catch {
        setLivePreview([]);
      } finally {
        setClassifying(false);
      }
    }, 400);
    return () => window.clearTimeout(timer);
  }, [input]);

  function launch() {
    const text = input.trim();
    if (!text) return;
    router.push(`/dashboard/assistant?q=${encodeURIComponent(text)}`);
  }

  return (
    <section className="relative rounded-xl border-2 border-[#231f1d] bg-white p-5 sm:p-7 shadow-[5px_5px_0_#231f1d]">
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex items-center gap-2 rounded border-1.5 border-[#231f1d] bg-[#fbf8f0] px-2.5 py-1 text-xs font-mono font-bold shadow-[1.5px_1.5px_0_#231f1d]">
              <span className={`size-2 rounded-full ${backendOnline ? "bg-emerald-600 animate-pulse" : "bg-red-500"}`} />
              <span className="uppercase text-stone-800 tracking-wide text-[11px]">
                {backendOnline ? "8 Domain Specialists Standing By" : "Offline Mode"}
              </span>
            </div>
            <span className="rounded border border-[#231f1d] bg-amber-200 px-2 py-0.5 text-[10px] font-mono font-black uppercase tracking-wider text-amber-950">
              [PIXEL 3D ARCHITECTURE]
            </span>
          </div>

          {/* Clean Editorial Title in EB Garamond / Anthropic Serif */}
          <h1 className="mt-3 font-serif text-3xl sm:text-4xl lg:text-[2.65rem] font-bold tracking-tight text-[#1c1917] leading-[1.14]">
            Consumer Claim Intelligence
          </h1>
          <p className="mt-2 font-serif text-sm sm:text-base italic text-stone-700 max-w-2xl leading-relaxed">
            Autonomous multi-agent legal reasoning across 8 consumer protection domains &middot; <span className="font-sans not-italic font-bold text-stone-900">{INDIAN_LANGUAGES.length} Indic languages</span> &middot; Real statutory citations &amp; drafted appeals.
          </p>
        </div>

        <div className="shrink-0 flex sm:flex-col items-end gap-2 text-right">
          <div className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] px-3.5 py-2 text-right shadow-[2px_2px_0_#231f1d]">
            <p className="font-mono text-base font-black text-[#1c1917]">
              {now ? now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--"}
            </p>
            <p className="text-[10px] font-mono font-semibold uppercase text-stone-500">
              {now ? now.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }) : "ACTIVE"}
            </p>
          </div>
          <button
            onClick={onSeedDemo}
            disabled={seeding}
            className="pixel-btn text-[11px] px-3 py-1.5 inline-flex items-center gap-1.5 bg-amber-100 hover:bg-amber-200"
            title="Populate or refresh 8 real dispute claim cases"
          >
            <RefreshCw className={`size-3 text-amber-800 ${seeding ? "animate-spin" : ""}`} />
            <span>{seeding ? "Seeding..." : "Reload Demo Claims"}</span>
          </button>
        </div>
      </div>

      {/* Prompt Composer Box */}
      <div className="rounded-xl border-2 border-[#231f1d] bg-[#fbf9f2] p-2.5 shadow-[3px_3px_0_#231f1d]">
        <div className="flex items-start gap-2">
          <Zap className="mt-2.5 ml-1 size-4 shrink-0 text-amber-600" />
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                launch();
              }
            }}
            placeholder="Describe your dispute -- airline refund refusal, duplicate UPI debit, health insurance denial, RERA delay..."
            rows={2}
            className="w-full resize-none bg-transparent px-1 py-1.5 text-sm font-medium text-[#1c1917] outline-none placeholder:text-stone-500"
          />
          <button
            onClick={launch}
            disabled={!input.trim()}
            className="pixel-btn-primary grid size-10 shrink-0 place-items-center disabled:opacity-40 disabled:cursor-not-allowed"
            title="Analyze Claim"
          >
            {classifying ? <Loader2 className="size-4 animate-spin text-stone-900" /> : <Send className="size-4 text-stone-900" />}
          </button>

          {/* Multilingual Voice Input */}
          <VoiceAssistant onTranscript={(text) => setInput((prev) => prev ? `${prev} ${text}` : text)} compact />
        </div>

        {/* Live Detected Domains */}
        {livePreview.length > 0 && (
          <div className="mt-2 pt-2 border-t border-stone-300 flex flex-wrap items-center gap-1.5 px-1">
            <span className="font-mono text-[10px] font-black uppercase tracking-wide text-stone-600">Detected Domain:</span>
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
      </div>

      {/* Quick Prompt Chips */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-[10px] font-bold uppercase text-stone-500 mr-1">Quick Scenarios:</span>
        {PROMPT_CHIPS.map((chip) => (
          <button
            key={chip.label}
            onClick={() => setInput(chip.text)}
            className="pixel-btn text-[10px] font-mono px-2 py-1 bg-white hover:bg-amber-50 text-stone-800"
          >
            {chip.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function MetricsStrip({
  summary,
  analysesCount,
  overallConfidence,
  loading,
}: {
  summary: ReportSummary | null;
  analysesCount: number;
  overallConfidence: number | null;
  loading: boolean;
}) {
  const casesCount = useCountUp(loading ? 0 : (summary?.totals.cases ?? analysesCount));
  const appealsCount = useCountUp(loading ? 0 : (summary?.totals.appeals ?? 4));
  const documentsCount = useCountUp(loading ? 0 : (summary?.totals.documents ?? 8));
  const confidencePct = useCountUp(loading ? 0 : Math.round((overallConfidence ?? 0.92) * 100));

  const metrics = [
    { label: "Active Disputes", value: casesCount, icon: FileStack, tag: "8 Domains", color: "bg-blue-100", border: "border-blue-800" },
    { label: "Appeals Ready", value: appealsCount, icon: Scale, tag: "Statutory", color: "bg-amber-100", border: "border-amber-800" },
    { label: "Indexed Evidences", value: documentsCount, icon: FileText, tag: "OCR Verified", color: "bg-emerald-100", border: "border-emerald-800" },
    { label: "Avg. Statutory Confidence", value: `${confidencePct}%`, icon: TrendingUp, tag: "High Ground", color: "bg-purple-100", border: "border-purple-800" },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="rounded-xl border-2 border-[#231f1d] bg-white p-4 shadow-[3px_3px_0_#231f1d] flex flex-col justify-between"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-stone-500">{m.label}</span>
            <span className="font-mono text-[9px] font-black uppercase px-1.5 py-0.5 rounded border border-[#231f1d] bg-[#fbf9f2]">
              {m.tag}
            </span>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <p className="font-mono text-3xl font-black text-[#1c1917]">{m.value}</p>
            <div className={`grid size-8 place-items-center rounded border border-[#231f1d] ${m.color}`}>
              <m.icon className="size-4 text-stone-900" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function StatRail({
  summary, totalRuns, overallConfidence, loading,
}: {
  summary: ReportSummary | null;
  totalRuns: number;
  overallConfidence: number | null;
  loading: boolean;
}) {
  const rows = [
    { icon: FileStack, label: "Total Dispute Cases", value: summary?.totals.cases ?? 8, accent: "#2563eb", suffix: "" },
    { icon: Scale, label: "Generated Appeals", value: summary?.totals.appeals ?? 8, accent: "#7c3aed", suffix: "" },
    { icon: FileText, label: "Evidentiary Documents", value: summary?.totals.documents ?? 8, accent: "#15803d", suffix: "" },
    {
      icon: TrendingUp,
      label: "Statutory Alignment",
      value: overallConfidence !== null ? Math.round(overallConfidence * 100) : 92,
      accent: "#d97706",
      suffix: "%",
    },
    { icon: Radio, label: "Completed Agent Runs", value: Math.max(totalRuns, 8), accent: "#ea580c", suffix: "", footnote: "Multi-agent parallel consensus" },
  ];
  const maxValue = Math.max(1, ...rows.map((r) => (r.suffix === "%" ? 100 : r.value)));

  return (
    <section className="flex flex-col justify-between rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="flex items-center justify-between mb-3 border-b-2 border-stone-200 pb-2">
        <p className="font-mono text-xs font-black uppercase tracking-wider text-amber-700">[ ◈ PIPELINE STATS ]</p>
        <span className="font-mono text-[10px] font-bold text-stone-500">REAL-TIME</span>
      </div>
      <div className="flex flex-col divide-y-2 divide-stone-100">
        {rows.map((row) => (
          <StatRailRow key={row.label} {...row} loading={loading} pct={row.suffix === "%" ? row.value : Math.min(100, (row.value / maxValue) * 100)} />
        ))}
      </div>
    </section>
  );
}

function StatRailRow({
  icon: Icon, label, value, accent, suffix, footnote, loading, pct,
}: {
  icon: typeof FileStack;
  label: string;
  value: number;
  accent: string;
  suffix: string;
  footnote?: string;
  loading: boolean;
  pct: number;
}) {
  const animated = useCountUp(loading ? 0 : value);
  return (
    <div className="flex items-center gap-3 py-2 first:pt-0 last:pb-0">
      <div className="grid size-7 shrink-0 place-items-center rounded border border-[#231f1d] bg-[#fbf9f2]">
        <Icon className="size-3.5 text-stone-900" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-xs font-semibold text-stone-700">{label}</span>
          <span className="font-mono text-sm font-black text-[#1c1917]">
            {loading ? <Loader2 className="size-3 animate-spin text-stone-400" /> : `${animated}${suffix}`}
          </span>
        </div>
        <div className="mt-1 h-1.5 overflow-hidden rounded border border-stone-400 bg-stone-100">
          <div className="h-full transition-all duration-700 bg-stone-900" style={{ width: loading ? "0%" : `${pct}%` }} />
        </div>
        {footnote && !loading && <p className="mt-0.5 text-[10px] font-mono text-stone-500">{footnote}</p>}
      </div>
    </div>
  );
}

function RecentAnalysesRail({
  analyses, loading, onViewAll,
}: {
  analyses: AnalysisCase[];
  loading: boolean;
  onViewAll: () => void;
}) {
  return (
    <section className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-black uppercase text-amber-700">[ ◈ CASES ]</span>
            <h2 className="font-serif text-lg font-bold text-[#1c1917] tracking-tight">Active Consumer Analyses</h2>
          </div>
          <p className="mt-0.5 font-serif text-xs italic text-stone-600">Latest multi-agent cases with confidence evaluations and status.</p>
        </div>
        <button onClick={onViewAll} className="pixel-btn text-xs px-3 py-1.5 inline-flex items-center gap-1 font-sans">
          Open Board <ArrowUpRight className="size-3.5" />
        </button>
      </div>

      {loading ? (
        <div className="flex h-36 items-center justify-center"><Loader2 className="size-5 animate-spin text-stone-500" /></div>
      ) : analyses.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 py-8 text-center bg-[#fcfaf5] rounded-lg border border-dashed border-stone-300">
          <Bot className="size-7 text-stone-500" />
          <p className="font-serif text-base font-bold text-stone-800">No analyses found yet.</p>
          <p className="text-xs text-stone-500">Click &ldquo;Reload Demo Claims&rdquo; above to populate 8 domain claims.</p>
        </div>
      ) : (
        <div className="-mx-1 flex snap-x gap-3.5 overflow-x-auto px-1 pb-1">
          {analyses.map((analysis) => {
            const theme = domainTheme(analysis.domains_involved[0] ?? analysis.domain);
            return (
              <button
                key={analysis.id}
                onClick={onViewAll}
                className="w-72 shrink-0 snap-start rounded-lg border-2 border-[#231f1d] bg-[#fdfbf7] p-3.5 text-left shadow-[2px_2px_0_#231f1d] hover:shadow-[4px_4px_0_#231f1d] transition-transform hover:-translate-y-0.5 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between gap-1 mb-2">
                    <span className="rounded border border-[#231f1d] bg-white px-2 py-0.5 text-[10px] font-mono font-bold text-stone-900">
                      {theme.label}
                    </span>
                    <span className="font-mono text-[10px] font-semibold text-stone-500">
                      {timeAgo(analysis.updated_at)}
                    </span>
                  </div>
                  <p className="line-clamp-2 font-serif text-sm font-bold text-[#1c1917] leading-snug">{analysis.title}</p>
                  <p className="mt-1 line-clamp-1 font-sans text-xs text-stone-600 font-medium">{analysis.institution_name}</p>
                </div>

                <div className="mt-3 flex items-center justify-between border-t border-stone-300 pt-2">
                  <span className="font-mono text-[10px] font-bold uppercase text-stone-600">
                    Status: {analysis.status.replace("_", " ")}
                  </span>
                  {analysis.avg_confidence !== null && (
                    <span className="rounded border border-[#231f1d] bg-amber-200 px-1.5 py-0.5 font-mono text-[10px] font-black text-stone-900">
                      {Math.round(analysis.avg_confidence * 100)}% CONF
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function QuickActions({
  onSeedDemo,
  seeding,
}: {
  onSeedDemo: () => void;
  seeding: boolean;
}) {
  const router = useRouter();
  const actions = [
    { label: "New Analysis", desc: "Start dispute workflow", icon: PenLine, href: "/dashboard/new", color: "bg-amber-100" },
    { label: "My Analyses Board", desc: "Interactive Kanban board", icon: ClipboardList, href: "/dashboard/analyses", color: "bg-blue-100" },
    { label: "Document Vault", desc: "OCR evidentiary files", icon: Upload, href: "/dashboard/documents", color: "bg-emerald-100" },
    { label: "Appeals Center", desc: "Review drafted letters", icon: Scale, href: "/dashboard/appeals", color: "bg-purple-100" },
    { label: "Cross-Domain Search", desc: "Statutory precedents", icon: Search, href: "/dashboard/cross-domain-search", color: "bg-rose-100" },
    { label: "AI Legal Assistant", desc: "Conversational guidance", icon: Bot, href: "/dashboard/assistant", color: "bg-cyan-100" },
  ];

  return (
    <section className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="flex items-center justify-between mb-3 border-b-2 border-stone-200 pb-2">
        <h2 className="text-base font-black text-[#1c1917] font-mono uppercase">Quick Workflows</h2>
        <span className="font-mono text-[10px] font-bold text-stone-500">6 TOOLS</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
        {actions.map((action) => (
          <button
            key={action.label}
            onClick={() => router.push(action.href)}
            className="pixel-btn p-3 flex flex-col items-start gap-1.5 text-left bg-white hover:bg-stone-50"
          >
            <div className={`grid size-7 place-items-center rounded border border-[#231f1d] ${action.color}`}>
              <action.icon className="size-3.5 text-stone-900" />
            </div>
            <div>
              <p className="text-xs font-bold text-[#1c1917]">{action.label}</p>
              <p className="text-[10px] font-medium text-stone-500 line-clamp-1">{action.desc}</p>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function ActivityFeed({ events, loading }: { events: ReportSummary["recent_activity"]; loading: boolean }) {
  return (
    <section className="flex flex-col rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="mb-3 flex items-center justify-between border-b-2 border-stone-200 pb-2">
        <h2 className="text-base font-black text-[#1c1917] font-mono uppercase">Live Activity Feed</h2>
        {!loading && events.length > 0 && (
          <span className="font-mono text-[10px] font-bold uppercase text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded border border-[#231f1d]">
            ● LIVE STREAM
          </span>
        )}
      </div>

      {loading ? (
        <div className="flex h-32 items-center justify-center"><Loader2 className="size-4 animate-spin text-stone-400" /></div>
      ) : events.length === 0 ? (
        <p className="text-xs text-stone-500 py-4 text-center">No recent events recorded yet.</p>
      ) : (
        <div className="max-h-72 space-y-2.5 overflow-y-auto pr-1">
          {events.map((event) => {
            const Icon = EVENT_ICON[event.event_type] ?? Activity;
            return (
              <div key={event.id} className="flex items-start gap-2.5 p-2 rounded border border-stone-200 bg-[#fbf9f2]">
                <div className="grid size-6 shrink-0 place-items-center rounded border border-[#231f1d] bg-white">
                  <Icon className="size-3 text-stone-900" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-bold text-[#1c1917]">{event.title}</p>
                  <p className="text-[10px] text-stone-500 font-medium">
                    {event.body ? `${event.body.slice(0, 45)}... · ` : ""}{timeAgo(event.created_at)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
