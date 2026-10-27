"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileText, Mail, AlertTriangle, Scale, Search, Copy, Download, Check, Loader2,
  Sparkles, ChevronRight, Send, Inbox, Clock, CheckCircle2, ArrowUpCircle,
  FolderOpen, Wand2, Volume2,
} from "lucide-react";
import {
  listAppeals, runMultiDomainCase, updateAppealStatus, classifyQuery, listAnalyses, getCaseReport,
  type Appeal, type DomainCandidate, type AnalysisCase,
} from "@/lib/api-client";
import { ReasoningLanes } from "@/components/chat/ReasoningLanes";
import { domainTheme } from "@/components/chat/domain-theme";
import { markdownComponents } from "@/components/chat/markdown-components";
import { ESTIMATED_STAGES } from "@/components/chat/pipeline";
import { VoiceAssistant } from "@/components/chat/VoiceAssistant";
import { getVoiceEngine } from "@/lib/voice-engine";

const DOC_TYPE_META: Record<string, { label: string; icon: typeof FileText }> = {
  appeal_letter: { label: "Appeal Letter", icon: FileText },
  complaint_email: { label: "Complaint Email", icon: Mail },
  escalation_note: { label: "Escalation Note", icon: AlertTriangle },
  consumer_complaint: { label: "Consumer Complaint", icon: Scale },
};

const STATUS_META: Record<Appeal["status"], { label: string; color: string; bg: string; icon: typeof Clock }> = {
  draft: { label: "Draft", color: "#1c1917", bg: "#f3f0e6", icon: Clock },
  sent: { label: "Sent", color: "#0369a1", bg: "#e0f2fe", icon: Send },
  escalated: { label: "Escalated", color: "#b45309", bg: "#fef3c7", icon: ArrowUpCircle },
  resolved: { label: "Resolved", color: "#15803d", bg: "#dcfce7", icon: CheckCircle2 },
};

const STATUS_ORDER: Appeal["status"][] = ["draft", "sent", "escalated", "resolved"];

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function AppealsCenter() {
  const [appeals, setAppeals] = useState<Appeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<Appeal["status"] | "all">("all");
  const [search, setSearch] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genQuery, setGenQuery] = useState("");
  const [genDomains, setGenDomains] = useState<DomainCandidate[]>([]);
  const [filledCount, setFilledCount] = useState(0);
  const [genError, setGenError] = useState<string | null>(null);
  const stageTimerRef = useRef<number | null>(null);

  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [analysesLoading, setAnalysesLoading] = useState(true);
  const [generatingCaseId, setGeneratingCaseId] = useState<string | null>(null);
  const [caseGenError, setCaseGenError] = useState<string | null>(null);

  async function refresh() {
    try {
      const data = await listAppeals();
      setAppeals(data);
      return data;
    } catch {
      return [];
    } finally {
      setLoading(false);
    }
  }

  async function refreshAnalyses() {
    try {
      setAnalyses(await listAnalyses());
    } catch {
      // keep last-known list
    } finally {
      setAnalysesLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    refreshAnalyses();
  }, []);

  async function generateFromCase(analysis: AnalysisCase) {
    if (generatingCaseId) return;
    setGeneratingCaseId(analysis.id);
    setCaseGenError(null);
    try {
      let problemDescription = analysis.title;
      try {
        const fullReport = await getCaseReport(analysis.id);
        if (fullReport.latest_analysis?.final_report) {
          problemDescription = `${analysis.title}\n\nEvidence Summary:\n${fullReport.latest_analysis.final_report.slice(0, 800)}`;
        }
      } catch {}

      const newCaseId = crypto.randomUUID();
      const response = await runMultiDomainCase(newCaseId, problemDescription);
      const updated = await refresh();

      const forThisDomain = updated.filter((a) =>
        (response.domains_analyzed.includes(a.domain ?? "") || a.title.includes(analysis.title.slice(0, 20)))
      );
      const newest = forThisDomain.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
      if (newest) setSelectedId(newest.id);
      else if (updated.length > 0) setSelectedId(updated[0].id);
    } catch (err) {
      setCaseGenError(err instanceof Error ? err.message : "Failed to draft appeal from this case.");
    } finally {
      setGeneratingCaseId(null);
    }
  }

  useEffect(() => {
    if (!genQuery || genQuery.trim().length < 12) {
      setGenDomains([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        setGenDomains((await classifyQuery(genQuery)).candidates);
      } catch {
        setGenDomains([]);
      }
    }, 450);
    return () => window.clearTimeout(timer);
  }, [genQuery]);

  const filtered = useMemo(() => {
    return appeals.filter((a) => {
      if (statusFilter !== "all" && a.status !== statusFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          a.title.toLowerCase().includes(q) ||
          a.content.toLowerCase().includes(q) ||
          (a.domain ?? "").toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [appeals, statusFilter, search]);

  useEffect(() => {
    if (filtered.length > 0 && (!selectedId || !filtered.some((a) => a.id === selectedId))) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId]);

  const selected = useMemo(() => appeals.find((a) => a.id === selectedId) ?? null, [appeals, selectedId]);

  async function generate() {
    const q = genQuery.trim();
    if (!q || generating) return;
    setGenerating(true);
    setGenError(null);
    setFilledCount(0);

    let stage = 0;
    stageTimerRef.current = window.setInterval(() => {
      stage = Math.min(stage + 1, ESTIMATED_STAGES.length);
      setFilledCount(stage);
    }, 1300);

    try {
      const caseId = crypto.randomUUID();
      await runMultiDomainCase(caseId, q);
      setGenQuery("");
      setGenDomains([]);
      const updated = await refresh();
      if (updated.length > 0) {
        const sorted = [...updated].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        setSelectedId(sorted[0].id);
      }
    } catch (err) {
      setGenError(err instanceof Error ? err.message : "Failed to draft appeal. Is the backend running?");
    } finally {
      if (stageTimerRef.current) window.clearInterval(stageTimerRef.current);
      setGenerating(false);
      setFilledCount(0);
    }
  }

  async function changeStatus(appeal: Appeal, status: Appeal["status"]) {
    setAppeals((current) => current.map((a) => (a.id === appeal.id ? { ...a, status } : a)));
    try {
      await updateAppealStatus(appeal.id, status);
    } catch {
      refresh();
    }
  }

  return (
    <div className="flex min-h-[720px] flex-1 flex-col gap-4 xl:flex-row">
      {/* List pane */}
      <div className="flex w-full flex-col rounded-xl border-2 border-[#231f1d] bg-white shadow-[4px_4px_0_#231f1d] xl:w-[400px]">
        <div className="border-b-2 border-stone-200 p-4 bg-[#fbf9f2]">
          <CaseAppealPicker
            analyses={analyses}
            loading={analysesLoading}
            appeals={appeals}
            generatingCaseId={generatingCaseId}
            onGenerate={generateFromCase}
          />
          {caseGenError && <p className="mt-2 text-xs font-bold text-red-600">{caseGenError}</p>}

          <div className="my-3 flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-wide text-stone-500">
            <span className="h-px flex-1 bg-stone-300" /> or describe a new dispute <span className="h-px flex-1 bg-stone-300" />
          </div>

          <GenerateBar
            query={genQuery}
            setQuery={setGenQuery}
            onGenerate={generate}
            generating={generating}
            domains={genDomains}
          />
          {generating && (
            <div className="mt-3">
              <ReasoningLanes
                lanes={(genDomains.length ? genDomains.map((d) => d.domain) : ["health_insurance"]).map((domain) => ({ domain }))}
                processing
                filledCount={filledCount}
              />
            </div>
          )}
          {genError && <p className="mt-2 text-xs font-bold text-red-600">{genError}</p>}
        </div>

        <div className="flex items-center gap-2 border-b-2 border-stone-200 p-3 bg-white">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-stone-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search appeals by keyword or domain..."
              className="w-full rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] py-1.5 pl-8 pr-2 text-xs font-medium text-stone-900 outline-none shadow-[1.5px_1.5px_0_#231f1d] focus:border-amber-600 placeholder:text-stone-400"
            />
          </div>
        </div>

        <div className="flex gap-1.5 overflow-x-auto border-b-2 border-stone-200 p-2 bg-[#fcfaf5]">
          <FilterChip label="All" active={statusFilter === "all"} onClick={() => setStatusFilter("all")} count={appeals.length} />
          {STATUS_ORDER.map((status) => (
            <FilterChip
              key={status}
              label={STATUS_META[status].label}
              active={statusFilter === status}
              onClick={() => setStatusFilter(status)}
              count={appeals.filter((a) => a.status === status).length}
              color={STATUS_META[status].color}
            />
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-2 bg-white">
          {loading ? (
            <div className="flex h-full items-center justify-center text-stone-500 py-12">
              <Loader2 className="size-5 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center py-12">
              <Inbox className="size-8 text-stone-400" />
              <p className="text-xs font-medium text-stone-600">
                {appeals.length === 0 ? "No appeals generated yet -- use voice or text above." : "No appeals match this filter."}
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {filtered.map((appeal) => (
                <AppealRow key={appeal.id} appeal={appeal} active={selected?.id === appeal.id} onClick={() => setSelectedId(appeal.id)} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Detail pane */}
      <div className="flex-1 rounded-xl border-2 border-[#231f1d] bg-white shadow-[4px_4px_0_#231f1d] overflow-hidden">
        {selected ? (
          <AppealDocument appeal={selected} onStatusChange={(status) => changeStatus(selected, status)} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center p-8 text-center text-stone-500">
            <Scale className="size-12 text-stone-300 mb-3" />
            <p className="font-mono text-xs font-bold uppercase text-stone-700">Select an appeal to view drafted legal notices</p>
            <p className="text-xs text-stone-500 mt-1 max-w-sm">Every draft includes statutory references, turnaround penalties, and Ombudsman escalation clauses.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function CaseAppealPicker({
  analyses, loading, appeals, generatingCaseId, onGenerate,
}: {
  analyses: AnalysisCase[];
  loading: boolean;
  appeals: Appeal[];
  generatingCaseId: string | null;
  onGenerate: (analysis: AnalysisCase) => void;
}) {
  const appealCountByCase = useMemo(() => {
    const map = new Map<string, number>();
    for (const a of appeals) {
      if (a.case_id) map.set(a.case_id, (map.get(a.case_id) ?? 0) + 1);
    }
    return map;
  }, [appeals]);

  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 font-mono text-[10px] font-black uppercase text-stone-800">
        <FolderOpen className="size-3.5 text-amber-700" /> Draft from existing case analysis
      </p>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-stone-500 py-1">
          <Loader2 className="size-3 animate-spin" /> Loading cases...
        </div>
      ) : analyses.length === 0 ? (
        <div className="rounded-lg border border-stone-300 bg-white p-2 text-center text-xs text-stone-500">
          No analyses yet -- run one in New Analysis first.
        </div>
      ) : (
        <div className="max-h-40 space-y-1.5 overflow-y-auto pr-0.5">
          {analyses.map((analysis) => {
            const theme = domainTheme(analysis.domain);
            const existing = appealCountByCase.get(analysis.id) ?? 0;
            const isGenerating = generatingCaseId === analysis.id;
            return (
              <div
                key={analysis.id}
                className="flex items-center gap-2 rounded-lg border-2 border-[#231f1d] bg-white p-2 shadow-[1.5px_1.5px_0_#231f1d]"
              >
                <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: theme.color }} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[11px] font-bold text-stone-900">{analysis.title || theme.label}</p>
                  <p className="truncate font-mono text-[9px] text-stone-500">
                    {theme.label}
                    {existing > 0 ? ` · ${existing} appeal${existing === 1 ? "" : "s"} generated` : ""}
                  </p>
                </div>
                <button
                  onClick={() => onGenerate(analysis)}
                  disabled={generatingCaseId !== null}
                  className="pixel-btn flex shrink-0 items-center gap-1 px-2 py-1 text-[10px]"
                >
                  {isGenerating ? <Loader2 className="size-3 animate-spin" /> : <Wand2 className="size-3" />}
                  {isGenerating ? "Drafting" : "Draft Appeal"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GenerateBar({
  query, setQuery, onGenerate, generating, domains,
}: {
  query: string;
  setQuery: (v: string) => void;
  onGenerate: () => void;
  generating: boolean;
  domains: DomainCandidate[];
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-1.5 font-mono text-[10px] font-black uppercase text-stone-800">
          <Sparkles className="size-3.5 text-amber-700" /> New Voice / Text Appeal
        </p>
        <VoiceAssistant compact onTranscript={(text) => setQuery(query ? `${query} ${text}` : text)} />
      </div>
      <div className="flex items-center gap-1.5">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onGenerate()}
          placeholder="Speak or describe: e.g. IndiGo cancelled flight, refused compensation..."
          className="flex-1 rounded-lg border-2 border-[#231f1d] bg-white px-2.5 py-1.5 text-xs text-stone-900 shadow-[2px_2px_0_#231f1d] outline-none placeholder:text-stone-400 focus:border-amber-600"
        />
        <button
          onClick={onGenerate}
          disabled={generating || !query.trim()}
          className="pixel-btn-primary grid size-8 shrink-0 place-items-center rounded-lg disabled:cursor-not-allowed disabled:opacity-40"
        >
          {generating ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
        </button>
      </div>
      {domains.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {domains.map((d) => {
            const theme = domainTheme(d.domain);
            return (
              <span key={d.domain} className="rounded border border-[#231f1d] bg-white px-1.5 py-0.5 text-[9px] font-mono font-bold shadow-[1px_1px_0_#231f1d]" style={{ color: theme.color }}>
                {theme.label}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

function FilterChip({ label, active, onClick, count, color }: { label: string; active: boolean; onClick: () => void; count: number; color?: string }) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 rounded border-2 border-[#231f1d] px-2.5 py-1 text-[10px] font-mono font-bold transition-all shadow-[1.5px_1.5px_0_#231f1d] ${
        active ? "bg-amber-300 text-stone-900" : "bg-white text-stone-700 hover:bg-stone-100"
      }`}
    >
      {label} <span className="opacity-70 font-sans">({count})</span>
    </button>
  );
}

function AppealRow({ appeal, active, onClick }: { appeal: Appeal; active: boolean; onClick: () => void }) {
  const docMeta = DOC_TYPE_META[appeal.document_type] ?? DOC_TYPE_META.appeal_letter;
  const statusMeta = STATUS_META[appeal.status] ?? STATUS_META.draft;
  const theme = domainTheme(appeal.domain ?? "");
  const Icon = docMeta.icon;


  return (
    <button
      onClick={onClick}
      className={`flex w-full items-start gap-2.5 rounded-lg border-2 border-[#231f1d] p-2.5 text-left transition-all ${
        active ? "bg-amber-100 shadow-[3px_3px_0_#231f1d] font-bold" : "bg-white hover:bg-[#fbf9f2] shadow-[2px_2px_0_#231f1d]"
      }`}
    >
      <div className="grid size-8 shrink-0 place-items-center rounded border border-[#231f1d] bg-[#fcfaf5]" style={{ borderColor: theme.color }}>
        <Icon className="size-3.5" style={{ color: theme.color }} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-serif text-sm font-bold text-stone-900">{appeal.title}</p>
        <div className="mt-1 flex items-center gap-1.5 font-sans">
          <span className="rounded border border-[#231f1d] px-1.5 py-0.2 text-[9px] font-mono font-bold uppercase shadow-[1px_1px_0_#231f1d]" style={{ backgroundColor: statusMeta.bg, color: statusMeta.color }}>
            {statusMeta.label}
          </span>
          <span className="text-[10px] font-mono text-stone-500">v{appeal.version} &middot; {timeAgo(appeal.created_at)}</span>
        </div>
      </div>
      <ChevronRight className={`mt-1.5 size-3.5 shrink-0 text-stone-400 transition-opacity ${active ? "opacity-100 text-stone-900" : "opacity-40"}`} />
    </button>
  );
}

function AppealDocument({ appeal, onStatusChange }: { appeal: Appeal; onStatusChange: (status: Appeal["status"]) => void }) {
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const docMeta = DOC_TYPE_META[appeal.document_type] ?? DOC_TYPE_META.appeal_letter;
  const theme = domainTheme(appeal.domain ?? "");
  const Icon = docMeta.icon;

  function copy() {
    navigator.clipboard.writeText(appeal.content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  function download() {
    const blob = new Blob([appeal.content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${appeal.document_type}-v${appeal.version}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function toggleSpeak() {
    const engine = getVoiceEngine();
    if (speaking) {
      engine.stopSpeaking();
      setSpeaking(false);
    } else {
      setSpeaking(true);
      try {
        const plainText = appeal.content
          .replace(/[#*`_\[\]()]/g, " ")
          .replace(/\s+/g, " ")
          .trim();
        await engine.speak(plainText);
      } catch {
      } finally {
        setSpeaking(false);
      }
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-stone-200 px-5 py-3.5 bg-[#fbf9f2]">
        <div className="flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-lg border-2 border-[#231f1d] bg-white shadow-[2px_2px_0_#231f1d]">
            <Icon className="size-5" style={{ color: theme.color }} />
          </div>
          <div>
            <p className="text-sm font-black font-mono text-stone-900">{docMeta.label}</p>
            <p className="font-mono text-[10px] text-stone-500">
              {theme.label} &middot; v{appeal.version} &middot; {timeAgo(appeal.created_at)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleSpeak}
            className={`pixel-btn inline-flex items-center gap-1 px-2.5 py-1 text-xs ${speaking ? "bg-amber-300 animate-pulse" : ""}`}
            title="Read notice aloud"
          >
            <Volume2 className="size-3.5" />
            <span>{speaking ? "Stop" : "Speak"}</span>
          </button>
          <StatusSelector status={appeal.status} onChange={onStatusChange} />
          <button onClick={copy} className="pixel-btn grid size-8 place-items-center" title="Copy content">
            {copied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
          </button>
          <button onClick={download} className="pixel-btn grid size-8 place-items-center" title="Download text">
            <Download className="size-3.5" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-5 bg-[#fcfaf5]">
        <div className="mx-auto max-w-2xl rounded-xl border-2 border-[#231f1d] bg-white p-6 shadow-[3px_3px_0_#231f1d]" style={{ borderTop: `4px solid ${theme.color}` }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {appeal.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

function StatusSelector({ status, onChange }: { status: Appeal["status"]; onChange: (status: Appeal["status"]) => void }) {
  const safeValue = STATUS_ORDER.includes(status) ? status : "draft";
  return (
    <select
      value={safeValue}
      onChange={(e) => onChange(e.target.value as Appeal["status"])}
      className="rounded-lg border-2 border-[#231f1d] bg-white px-2 py-1 text-xs font-bold text-stone-900 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
    >

      {STATUS_ORDER.map((s) => (
        <option key={s} value={s}>
          {STATUS_META[s].label}
        </option>
      ))}
    </select>
  );
}
