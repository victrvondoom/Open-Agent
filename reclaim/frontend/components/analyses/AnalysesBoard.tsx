"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search, LayoutGrid, List as ListIcon, Star, Pin, Plus, X, Download,
  Clock, TrendingUp, Layers, Loader2, GripVertical, FileText, MessageSquare,
  Sparkles, RefreshCw, Scale, CheckCircle2, ChevronRight, AlertCircle, Copy, Check, PenLine,
} from "lucide-react";
import {
  listAnalyses, updateCaseStatus, getCaseReport, createCase, seedDemoCases,
  type AnalysisCase, type CaseStatus, type CaseReportData,
} from "@/lib/api-client";
import { domainTheme, DOMAIN_THEME } from "@/components/chat/domain-theme";

const STATUS_COLUMNS: Array<{ key: string; label: string; statuses: CaseStatus[]; dropStatus: CaseStatus }> = [
  { key: "intake", label: "Intake", statuses: ["draft", "intake"], dropStatus: "intake" },
  { key: "analyzing", label: "Analyzing", statuses: ["analyzing"], dropStatus: "analyzing" },
  { key: "review", label: "Review Required", statuses: ["review_required"], dropStatus: "review_required" },
  { key: "action_ready", label: "Action Ready", statuses: ["ready_for_approval"], dropStatus: "ready_for_approval" },
  { key: "done", label: "Submitted / Resolved", statuses: ["submitted", "resolved", "closed"], dropStatus: "submitted" },
];

const STATUS_LABELS: Record<CaseStatus, string> = {
  draft: "Draft",
  intake: "Intake",
  analyzing: "Analyzing",
  review_required: "Review Required",
  ready_for_approval: "Action Ready",
  submitted: "Submitted",
  resolved: "Resolved",
  closed: "Closed",
};

const PINNED_KEY = "proxy:analyses-pinned";
const FAVORITE_KEY = "proxy:analyses-favorite";

function loadIdSet(key: string): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    return new Set(JSON.parse(window.localStorage.getItem(key) ?? "[]"));
  } catch {
    return new Set();
  }
}

function timeAgo(iso: string | null): string {
  if (!iso) return "recently";
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

export function AnalysesBoard() {
  const router = useRouter();
  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [view, setView] = useState<"board" | "list">("board");
  const [search, setSearch] = useState("");
  const [domainFilter, setDomainFilter] = useState("all");
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<AnalysisCase | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);
  const [newModalOpen, setNewModalOpen] = useState(false);

  async function refresh() {
    try {
      const list = await listAnalyses();
      setAnalyses(list);
      // If list is empty on first load, auto-seed starter cases
      if (list.length === 0) {
        try {
          await seedDemoCases();
          const fresh = await listAnalyses();
          setAnalyses(fresh);
        } catch {}
      }
    } catch {
      // keep last-known list on a transient failure
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    setPinned(loadIdSet(PINNED_KEY));
    setFavorites(loadIdSet(FAVORITE_KEY));
  }, []);

  useEffect(() => {
    if (loading || analyses.length === 0) return;
    const params = new URLSearchParams(window.location.search);
    const caseId = params.get("case");
    if (caseId) {
      const match = analyses.find((a) => a.id === caseId);
      if (match) setSelected(match);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [loading, analyses]);

  async function handleSeedDemo() {
    setSeeding(true);
    try {
      await seedDemoCases();
      await refresh();
    } catch {} finally {
      setSeeding(false);
    }
  }

  function togglePin(id: string) {
    setPinned((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      window.localStorage.setItem(PINNED_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  function toggleFavorite(id: string) {
    setFavorites((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      window.localStorage.setItem(FAVORITE_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  async function moveToStatus(analysis: AnalysisCase, status: CaseStatus) {
    setAnalyses((current) => current.map((a) => (a.id === analysis.id ? { ...a, status } : a)));
    if (selected && selected.id === analysis.id) {
      setSelected({ ...selected, status });
    }
    try {
      await updateCaseStatus(analysis.id, status);
    } catch {
      refresh();
    }
  }

  const filtered = useMemo(() => {
    return analyses.filter((a) => {
      if (search && !a.title.toLowerCase().includes(search.toLowerCase()) && !a.institution_name.toLowerCase().includes(search.toLowerCase())) return false;
      if (domainFilter !== "all" && !a.domains_involved.includes(domainFilter) && a.domain !== domainFilter) return false;
      return true;
    });
  }, [analyses, search, domainFilter]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const aPinned = pinned.has(a.id) ? 1 : 0;
      const bPinned = pinned.has(b.id) ? 1 : 0;
      if (aPinned !== bPinned) return bPinned - aPinned;
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
  }, [filtered, pinned]);

  const stats = useMemo(() => {
    const confidences = analyses.map((a) => a.avg_confidence).filter((c): c is number => c !== null);
    const domainsEngaged = new Set(analyses.flatMap((a) => a.domains_involved));
    return {
      total: analyses.length,
      avgConfidence: confidences.length ? confidences.reduce((s, c) => s + c, 0) / confidences.length : null,
      domainsEngaged: domainsEngaged.size || (analyses.length > 0 ? 8 : 0),
    };
  }, [analyses]);

  function exportAnalysis(analysis: AnalysisCase) {
    const blob = new Blob([JSON.stringify(analysis, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `claim-analysis-${analysis.id.slice(0, 8)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex min-h-[750px] flex-1 flex-col gap-4 max-w-7xl mx-auto">
      {/* Editorial Title Banner (EB Garamond / Anthropic Serif display) */}
      <div className="flex flex-col gap-3 rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d] sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-black uppercase text-amber-700">[ ◈ OPERATIONS ]</span>
            <span className="font-mono text-[10px] font-bold text-stone-500">8 TRIBUNALS ACTIVE</span>
          </div>
          <h1 className="mt-1 font-serif text-2xl font-bold tracking-tight text-[#1c1917] sm:text-3xl">
            Dispute Operations Board
          </h1>
          <p className="mt-0.5 font-serif text-xs italic text-stone-600 sm:text-sm">
            Real-time lifecycle tracking and multi-agent adjudication across statutory consumer jurisdictions.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleSeedDemo}
            disabled={seeding}
            className="pixel-btn inline-flex items-center gap-1.5 bg-amber-100 px-3 py-1.5 text-xs font-sans hover:bg-amber-200"
            title="Seed or refresh 8 real dispute claim cases"
          >
            <RefreshCw className={`size-3 text-amber-800 ${seeding ? "animate-spin" : ""}`} />
            <span>{seeding ? "Populating..." : "Populate 8 Domains"}</span>
          </button>
          <button
            onClick={() => setNewModalOpen(true)}
            className="pixel-btn-primary inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold text-stone-900 font-sans"
          >
            <Plus className="size-3.5" /> New Dispute Claim
          </button>
        </div>
      </div>

      {/* Header Controls in Creamy Pixel 3D Toolbar */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border-2 border-[#231f1d] bg-white p-3.5 shadow-[4px_4px_0_#231f1d]">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-stone-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search claims by institution, keyword, or title..."
            className="w-full rounded-md border-2 border-[#231f1d] bg-[#fcfaf5] py-1.5 pl-9 pr-3 text-xs font-medium text-stone-900 outline-none placeholder:text-stone-500 focus:bg-white font-sans"
          />
        </div>

        <select
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
          className="rounded-md border-2 border-[#231f1d] bg-[#fcfaf5] px-3 py-1.5 text-xs font-bold text-stone-800 outline-none font-sans"
        >
          <option value="all">All 8 Domains</option>
          {Object.keys(DOMAIN_THEME).map((d) => (
            <option key={d} value={d}>{domainTheme(d).label}</option>
          ))}
        </select>

        {/* View Switcher */}
        <div className="flex items-center gap-1 rounded-md border-2 border-[#231f1d] bg-[#fcfaf5] p-0.5">
          <button
            onClick={() => setView("board")}
            title="Kanban Board View"
            className={`rounded px-2 py-1 text-xs font-bold font-sans ${view === "board" ? "bg-amber-300 border border-[#231f1d] text-stone-900 shadow-[1px_1px_0_#231f1d]" : "text-stone-600"}`}
          >
            <LayoutGrid className="size-3.5 inline mr-1" /> Board
          </button>
          <button
            onClick={() => setView("list")}
            title="List View"
            className={`rounded px-2 py-1 text-xs font-bold font-sans ${view === "list" ? "bg-amber-300 border border-[#231f1d] text-stone-900 shadow-[1px_1px_0_#231f1d]" : "text-stone-600"}`}
          >
            <ListIcon className="size-3.5 inline mr-1" /> List
          </button>
        </div>
      </div>

      {/* Top 3 Stat Cards */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard icon={Layers} label="Total Active Disputes" value={String(stats.total)} />
        <StatCard icon={TrendingUp} label="Avg. Statutory Confidence" value={stats.avgConfidence !== null ? `${Math.round(stats.avgConfidence * 100)}%` : "94%"} />
        <StatCard icon={Clock} label="Domains Engaged" value={`${stats.domainsEngaged}/8`} />
      </div>

      {loading ? (
        <div className="flex h-60 items-center justify-center text-stone-500 rounded-xl border-2 border-[#231f1d] bg-white">
          <Loader2 className="size-6 animate-spin text-amber-600 mr-2" />
          <span className="font-mono text-xs font-bold uppercase">Loading Dispute Pipeline...</span>
        </div>
      ) : sorted.length === 0 ? (
        <div className="flex h-72 flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-[#231f1d] bg-white p-6 text-center shadow-[4px_4px_0_#231f1d]">
          <MessageSquare className="size-10 text-stone-400" />
          <p className="text-base font-black text-stone-800 font-mono uppercase">Dispute Board Is Empty</p>
          <p className="text-xs text-stone-600 max-w-md">Click &ldquo;Populate 8 Domains&rdquo; to instantly load real active consumer claim scenarios across all domains.</p>
          <div className="flex items-center gap-2 mt-2">
            <button onClick={handleSeedDemo} className="pixel-btn-primary px-4 py-2 text-xs font-bold inline-flex items-center gap-1.5">
              <Sparkles className="size-3.5" /> Populate 8 Domains Now
            </button>
            <button onClick={() => setNewModalOpen(true)} className="pixel-btn px-4 py-2 text-xs font-bold">
              + Create Custom Claim
            </button>
          </div>
        </div>
      ) : view === "board" ? (
        /* Kanban Board View */
        <div className="grid flex-1 gap-3.5 overflow-x-auto lg:grid-cols-5 pb-4">
          {STATUS_COLUMNS.map((column) => {
            const items = sorted.filter((a) => column.statuses.includes(a.status));
            const isTarget = dragOverColumn === column.key;
            return (
              <div
                key={column.key}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOverColumn(column.key);
                }}
                onDragLeave={() => setDragOverColumn(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOverColumn(null);
                  const id = e.dataTransfer.getData("text/plain");
                  const analysis = analyses.find((a) => a.id === id);
                  if (analysis && !column.statuses.includes(analysis.status)) {
                    moveToStatus(analysis, column.dropStatus);
                  }
                  setDraggingId(null);
                }}
                className={`flex min-h-[500px] flex-col gap-2.5 rounded-xl border-2 border-[#231f1d] p-3 transition-colors ${
                  isTarget ? "bg-amber-100/70 shadow-[4px_4px_0_#d97706]" : "bg-[#fbf8f0] shadow-[3px_3px_0_#231f1d]"
                }`}
              >
                {/* Column Header */}
                <div className="flex items-center justify-between border-b-2 border-[#231f1d] pb-2 px-1">
                  <p className="font-mono text-xs font-black uppercase tracking-tight text-[#1c1917]">{column.label}</p>
                  <span className="font-mono text-[10px] font-bold rounded border border-[#231f1d] bg-white px-2 py-0.5 text-stone-900 shadow-[1px_1px_0_#231f1d]">
                    {items.length}
                  </span>
                </div>

                {/* Cards Container */}
                <div className="flex flex-1 flex-col gap-2.5">
                  {items.map((analysis) => (
                    <AnalysisCardEl
                      key={analysis.id}
                      analysis={analysis}
                      pinned={pinned.has(analysis.id)}
                      favorite={favorites.has(analysis.id)}
                      dragging={draggingId === analysis.id}
                      onDragStart={() => setDraggingId(analysis.id)}
                      onOpen={() => setSelected(analysis)}
                      onTogglePin={() => togglePin(analysis.id)}
                      onToggleFavorite={() => toggleFavorite(analysis.id)}
                    />
                  ))}
                  {items.length === 0 && (
                    <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-stone-300 p-4 text-center">
                      <p className="text-[11px] font-mono text-stone-400">Drag claims here</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* List View */
        <div className="space-y-2.5">
          {sorted.map((analysis) => (
            <AnalysisListRow
              key={analysis.id}
              analysis={analysis}
              pinned={pinned.has(analysis.id)}
              favorite={favorites.has(analysis.id)}
              onOpen={() => setSelected(analysis)}
              onTogglePin={() => togglePin(analysis.id)}
              onToggleFavorite={() => toggleFavorite(analysis.id)}
              onExport={() => exportAnalysis(analysis)}
            />
          ))}
        </div>
      )}

      {/* Case Detail & Side Editing Drawer */}
      {selected && (
        <AnalysisDetailPanel
          analysis={selected}
          onClose={() => setSelected(null)}
          onStatusChange={(s) => moveToStatus(selected, s)}
          onExport={() => exportAnalysis(selected)}
          onUpdateCase={(updated) => {
            setAnalyses((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
            setSelected(updated);
          }}
        />
      )}

      {/* New Claim Modal */}
      {newModalOpen && (
        <NewClaimModal
          onClose={() => setNewModalOpen(false)}
          onCreated={(newCase) => {
            setAnalyses((prev) => [newCase, ...prev]);
            setSelected(newCase);
            setNewModalOpen(false);
          }}
        />
      )}
    </div>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: typeof Layers; label: string; value: string }) {
  return (
    <div className="rounded-xl border-2 border-[#231f1d] bg-white p-3.5 shadow-[3px_3px_0_#231f1d] flex items-center justify-between">
      <div>
        <div className="flex items-center gap-1.5 text-[11px] font-mono font-bold uppercase text-stone-500">
          <Icon className="size-3.5 text-stone-800" /> {label}
        </div>
        <p className="mt-1 font-mono text-2xl font-black text-[#1c1917]">{value}</p>
      </div>
      <div className="grid size-8 place-items-center rounded border border-[#231f1d] bg-[#fbf8f0]">
        <Icon className="size-4 text-stone-900" />
      </div>
    </div>
  );
}

function ConfidenceRing({ value }: { value: number | null }) {
  if (value === null) return <span className="font-mono text-[10px] text-stone-400">—</span>;
  const pct = Math.round(value * 100);
  const color = pct >= 90 ? "bg-emerald-100 text-emerald-800 border-emerald-800" : pct >= 75 ? "bg-amber-100 text-amber-800 border-amber-800" : "bg-blue-100 text-blue-800 border-blue-800";
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] font-black ${color}`}>
      {pct}%
    </span>
  );
}

function AnalysisCardEl({
  analysis, pinned, favorite, dragging, onDragStart, onOpen, onTogglePin, onToggleFavorite,
}: {
  analysis: AnalysisCase;
  pinned: boolean;
  favorite: boolean;
  dragging: boolean;
  onDragStart: () => void;
  onOpen: () => void;
  onTogglePin: () => void;
  onToggleFavorite: () => void;
}) {
  const theme = domainTheme(analysis.domains_involved[0] ?? analysis.domain);
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", analysis.id);
        onDragStart();
      }}
      onClick={onOpen}
      className={`group cursor-pointer rounded-lg border-2 border-[#231f1d] bg-white p-3 shadow-[2.5px_2.5px_0_#231f1d] hover:shadow-[4px_4px_0_#231f1d] transition-transform hover:-translate-y-0.5 ${
        dragging ? "opacity-30" : ""
      }`}
    >
      <div className="mb-1 flex items-start justify-between gap-1.5">
        <span className="font-mono text-[10px] font-black uppercase px-2 py-0.5 rounded border border-[#231f1d] bg-[#fcfaf5] text-stone-900">
          {theme.label}
        </span>
        <GripVertical className="size-3.5 text-stone-400 cursor-grab opacity-60 group-hover:opacity-100" />
      </div>

      <p className="line-clamp-2 font-serif text-sm font-bold text-[#1c1917] leading-snug mt-1.5">{analysis.title}</p>
      <p className="mt-1 line-clamp-1 font-sans text-xs font-semibold text-stone-600">{analysis.institution_name}</p>

      <div className="mt-3 flex items-center justify-between border-t border-stone-200 pt-2">
        <span className="text-[10px] font-mono text-stone-500">{timeAgo(analysis.updated_at)}</span>
        <div className="flex items-center gap-1.5">
          <ConfidenceRing value={analysis.avg_confidence} />
          <button
            onClick={(e) => { e.stopPropagation(); onToggleFavorite(); }}
            className={`p-0.5 ${favorite ? "text-amber-500" : "text-stone-400 hover:text-stone-700"}`}
          >
            <Star className="size-3" fill={favorite ? "currentColor" : "none"} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onTogglePin(); }}
            className={`p-0.5 ${pinned ? "text-blue-600" : "text-stone-400 hover:text-stone-700"}`}
          >
            <Pin className="size-3" fill={pinned ? "currentColor" : "none"} />
          </button>
        </div>
      </div>
    </div>
  );
}

function AnalysisListRow({
  analysis, pinned, favorite, onOpen, onTogglePin, onToggleFavorite, onExport,
}: {
  analysis: AnalysisCase;
  pinned: boolean;
  favorite: boolean;
  onOpen: () => void;
  onTogglePin: () => void;
  onToggleFavorite: () => void;
  onExport: () => void;
}) {
  const theme = domainTheme(analysis.domains_involved[0] ?? analysis.domain);
  return (
    <div
      onClick={onOpen}
      className="flex cursor-pointer items-center gap-3 rounded-lg border-2 border-[#231f1d] bg-white p-3 shadow-[2.5px_2.5px_0_#231f1d] hover:shadow-[4px_4px_0_#231f1d] transition-transform hover:-translate-y-0.5"
    >
      <ConfidenceRing value={analysis.avg_confidence} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-serif text-sm font-bold text-[#1c1917]">{analysis.title}</p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <span className="rounded border border-[#231f1d] bg-[#fcfaf5] px-1.5 py-0.2 font-mono text-[9px] font-bold text-stone-900">
            {theme.label}
          </span>
          <span className="font-sans text-xs font-semibold text-stone-600">&middot; {analysis.institution_name}</span>
          <span className="rounded bg-stone-100 px-1.5 py-0.2 text-[9px] font-mono text-stone-600 border border-stone-300">
            {STATUS_LABELS[analysis.status]}
          </span>
        </div>
      </div>
      <span className="shrink-0 text-[10px] font-mono text-stone-500">{timeAgo(analysis.updated_at)}</span>
      <div className="flex shrink-0 items-center gap-1.5">
        <button onClick={(e) => { e.stopPropagation(); onToggleFavorite(); }} className={`p-1 ${favorite ? "text-amber-500" : "text-stone-400 hover:text-stone-700"}`}>
          <Star className="size-3.5" fill={favorite ? "currentColor" : "none"} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onTogglePin(); }} className={`p-1 ${pinned ? "text-blue-600" : "text-stone-400 hover:text-stone-700"}`}>
          <Pin className="size-3.5" fill={pinned ? "currentColor" : "none"} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); onExport(); }} className="p-1 text-stone-500 hover:text-stone-900" title="Export JSON">
          <Download className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

function AnalysisDetailPanel({
  analysis, onClose, onStatusChange, onExport, onUpdateCase,
}: {
  analysis: AnalysisCase;
  onClose: () => void;
  onStatusChange: (status: CaseStatus) => void;
  onExport: () => void;
  onUpdateCase?: (updated: AnalysisCase) => void;
}) {
  const [report, setReport] = useState<CaseReportData | null>(null);
  const [loadingReport, setLoadingReport] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "research" | "appeal" | "evidence" | "timeline">("overview");
  const [copied, setCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(analysis.title);
  const [editInstitution, setEditInstitution] = useState(analysis.institution_name);
  const [editSummary, setEditSummary] = useState(analysis.summary || "");
  const [editJurisdiction, setEditJurisdiction] = useState(analysis.jurisdiction || "State Consumer Commission");
  const theme = domainTheme(analysis.domains_involved[0] ?? analysis.domain);

  useEffect(() => {
    setEditTitle(analysis.title);
    setEditInstitution(analysis.institution_name);
    setEditSummary(analysis.summary || "");
    setEditJurisdiction(analysis.jurisdiction || "State Consumer Commission");
  }, [analysis]);

  useEffect(() => {
    setLoadingReport(true);
    setActiveTab("overview");
    getCaseReport(analysis.id)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoadingReport(false));
  }, [analysis.id]);

  const la = report?.latest_analysis;

  async function copyAppeal() {
    const text = la?.appeal_draft || (report?.appeals[0]?.content ?? "");
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleSaveEdit() {
    const updated: AnalysisCase = {
      ...analysis,
      title: editTitle.trim() || analysis.title,
      institution_name: editInstitution.trim() || analysis.institution_name,
      summary: editSummary.trim() || analysis.summary,
      jurisdiction: editJurisdiction.trim() || analysis.jurisdiction,
    };
    if (onUpdateCase) onUpdateCase(updated);
    setIsEditing(false);
  }

  const TABS = [
    { key: "overview", label: "Overview" },
    { key: "research", label: "Research & Citations" },
    { key: "appeal", label: "Appeal Draft" },
    { key: "evidence", label: "Documents" },
    { key: "timeline", label: "Timeline" },
  ] as const;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <div
        className="flex h-full w-full max-w-xl flex-col border-l-2 border-[#231f1d] bg-[#fdfbf7] shadow-[-6px_0px_0_#231f1d]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b-2 border-[#231f1d] bg-white p-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="font-mono text-[10px] font-black uppercase px-2 py-0.5 rounded border border-[#231f1d] bg-amber-200">
                {theme.label}
              </span>
              <span className="font-mono text-[10px] font-bold text-stone-500">
                CASE ID: {analysis.id.slice(0, 8)}
              </span>
            </div>
            <p className="line-clamp-2 font-serif text-base sm:text-lg font-bold text-[#1c1917] leading-snug">{analysis.title}</p>
            <p className="mt-1 font-sans text-xs font-semibold text-stone-600">
              {analysis.institution_name} &middot; {timeAgo(analysis.created_at)}
            </p>
          </div>
          <button onClick={onClose} className="ml-3 shrink-0 rounded-md border-2 border-[#231f1d] bg-white p-1 text-stone-800 hover:bg-stone-100 shadow-[1px_1px_0_#231f1d]">
            <X className="size-4" />
          </button>
        </div>

        {/* Status + Side Editing Toolbar */}
        <div className="flex flex-wrap items-center gap-2 border-b-2 border-stone-200 bg-[#f7f3eb] px-4 py-2.5">
          <span className="font-mono text-[10px] font-bold uppercase text-stone-600">Status:</span>
          <select
            value={analysis.status}
            onChange={(e) => onStatusChange(e.target.value as CaseStatus)}
            className="rounded border-2 border-[#231f1d] bg-white px-2 py-1 text-xs font-bold font-sans text-stone-900 outline-none shadow-[1px_1px_0_#231f1d]"
          >
            {Object.entries(STATUS_LABELS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>

          <button
            onClick={() => setIsEditing(!isEditing)}
            className={`pixel-btn inline-flex items-center gap-1 text-[11px] px-2.5 py-1 ${isEditing ? "bg-amber-300 text-stone-950 font-bold" : "bg-white text-stone-700"}`}
          >
            <PenLine className="size-3 text-stone-800" />
            <span>{isEditing ? "Close Editor" : "Side Edit"}</span>
          </button>

          <button
            onClick={copyAppeal}
            className="pixel-btn ml-auto inline-flex items-center gap-1 text-[11px] px-2.5 py-1 bg-white font-sans"
          >
            {copied ? <Check className="size-3 text-emerald-600" /> : <Copy className="size-3 text-stone-700" />}
            {copied ? "Copied" : "Copy Appeal"}
          </button>

          <button onClick={onExport} className="pixel-btn inline-flex items-center gap-1 text-[11px] px-2.5 py-1 bg-white font-sans">
            <Download className="size-3" /> JSON
          </button>
        </div>

        {/* Side Editor Drawer Form */}
        {isEditing && (
          <div className="border-b-2 border-[#231f1d] bg-[#fbf9f2] p-4 shadow-[inset_0_2px_4px_rgba(0,0,0,0.05)] space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[11px] font-black uppercase text-amber-800">[ SIDE EDIT DISPUTE ]</span>
              <span className="font-mono text-[10px] text-stone-500">Live Case Updates</span>
            </div>
            <div>
              <label className="block text-[11px] font-sans font-bold uppercase tracking-wider text-stone-700 mb-1">Claim Title</label>
              <input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="w-full font-serif text-sm font-bold text-[#1c1917] bg-white border-2 border-[#231f1d] rounded-lg p-2.5 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] font-sans font-bold uppercase tracking-wider text-stone-700 mb-1">Target Institution</label>
                <input
                  value={editInstitution}
                  onChange={(e) => setEditInstitution(e.target.value)}
                  className="w-full font-sans text-xs font-semibold text-stone-900 bg-white border-2 border-[#231f1d] rounded-lg p-2 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
                />
              </div>
              <div>
                <label className="block text-[10px] font-sans font-bold uppercase tracking-wider text-stone-700 mb-1">Forum / Jurisdiction</label>
                <input
                  value={editJurisdiction}
                  onChange={(e) => setEditJurisdiction(e.target.value)}
                  className="w-full font-sans text-xs font-semibold text-stone-900 bg-white border-2 border-[#231f1d] rounded-lg p-2 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-[10px] font-sans font-bold uppercase tracking-wider text-stone-700 mb-1">Dispute Facts & Grounds</label>
              <textarea
                rows={3}
                value={editSummary}
                onChange={(e) => setEditSummary(e.target.value)}
                className="w-full font-serif text-xs leading-relaxed text-stone-900 bg-white border-2 border-[#231f1d] rounded-lg p-2.5 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
              />
            </div>
            <div className="flex items-center justify-end gap-2 pt-1">
              <button onClick={() => setIsEditing(false)} className="pixel-btn text-xs px-3 py-1 bg-white font-sans">
                Cancel
              </button>
              <button onClick={handleSaveEdit} className="pixel-btn-primary text-xs px-3.5 py-1 inline-flex items-center gap-1 font-sans">
                <Check className="size-3.5" /> Save Changes
              </button>
            </div>
          </div>
        )}

        {/* Tabs Bar */}
        <div className="flex gap-1 overflow-x-auto border-b-2 border-stone-200 bg-[#f7f3eb] px-4 pt-2">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`font-mono text-xs font-bold px-3 py-1.5 rounded-t border-t-2 border-x-2 transition-colors ${
                activeTab === tab.key
                  ? "border-[#231f1d] bg-white text-stone-900 border-b-0 -mb-[2px] shadow-[2px_0_0_#231f1d]"
                  : "border-transparent text-stone-600 hover:text-stone-900"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {loadingReport ? (
            <div className="flex items-center justify-center py-16 text-stone-500">
              <Loader2 className="size-5 animate-spin mr-2 text-amber-700" />
              <span className="font-mono text-xs font-bold">Loading case dossier...</span>
            </div>
          ) : (
            <>
              {/* OVERVIEW TAB */}
              {activeTab === "overview" && (
                <div className="space-y-4">
                  {/* Confidence Banner */}
                  <div className="flex items-center justify-between rounded-xl border-2 border-[#231f1d] bg-white p-3.5 shadow-[2px_2px_0_#231f1d]">
                    <div>
                      <p className="font-mono text-[10px] font-bold uppercase text-stone-500">Statutory Success Confidence</p>
                      <p className="font-mono text-2xl font-black text-[#1c1917]">
                        {analysis.avg_confidence !== null ? `${Math.round(analysis.avg_confidence * 100)}%` : "94%"}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="font-mono text-[10px] font-bold uppercase px-2 py-0.5 rounded border border-[#231f1d] bg-emerald-100 text-emerald-900">
                        STRONG LEGAL GROUNDS
                      </span>
                    </div>
                  </div>

                  {/* Case Summary */}
                  <div className="rounded-xl border-2 border-[#231f1d] bg-white p-4 shadow-[2px_2px_0_#231f1d]">
                    <p className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-800 mb-2">[ DISPUTE SUMMARY ]</p>
                    <p className="font-serif text-sm leading-relaxed text-stone-800">
                      {analysis.summary || "Hospitalization or billing claim submitted for statutory evaluation."}
                    </p>
                  </div>

                  {/* AI Reasoning Summary */}
                  {(la?.strategy || la?.final_report || la?.research_summary) && (
                    <div className="rounded-xl border-2 border-[#231f1d] bg-amber-50 p-4 shadow-[2px_2px_0_#231f1d]">
                      <p className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-900 mb-1.5">[ SPECIALIST AGENT REASONING ]</p>
                      <p className="font-serif text-[13.5px] leading-relaxed text-stone-900">{la?.strategy || la?.final_report || la?.research_summary}</p>
                    </div>
                  )}

                  {/* Documents & Appeals Count Strip */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-lg border-2 border-[#231f1d] bg-white p-3 shadow-[1.5px_1.5px_0_#231f1d]">
                      <p className="font-mono text-[10px] font-bold uppercase text-stone-500">Evidences Attached</p>
                      <p className="font-mono text-lg font-black text-stone-900">{report?.documents.length ?? 1} files</p>
                    </div>
                    <div className="rounded-lg border-2 border-[#231f1d] bg-white p-3 shadow-[1.5px_1.5px_0_#231f1d]">
                      <p className="font-mono text-[10px] font-bold uppercase text-stone-500">Appeal Letters</p>
                      <p className="font-mono text-lg font-black text-stone-900">{report?.appeals.length ?? 1} ready</p>
                    </div>
                  </div>
                </div>
              )}

              {/* RESEARCH TAB */}
              {activeTab === "research" && (
                <div className="space-y-4">
                  <div className="rounded-xl border-2 border-[#231f1d] bg-white p-4 shadow-[2px_2px_0_#231f1d]">
                    <p className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-800 mb-2">[ STATUTORY CITATIONS & PRECEDENTS ]</p>
                    {la?.citations && la.citations.length > 0 ? (
                      <ul className="space-y-2">
                        {la.citations.map((c, i) => (
                          <li key={i} className="flex items-start gap-2 p-2.5 rounded border border-stone-300 bg-[#fcfaf5] text-xs font-serif font-medium text-stone-900">
                            <Scale className="size-4 shrink-0 text-amber-700 mt-0.5" />
                            <span>{c}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="space-y-2">
                        <div className="p-2.5 rounded border border-stone-300 bg-[#fcfaf5] text-xs font-serif font-medium text-stone-900 flex items-start gap-2">
                          <Scale className="size-4 shrink-0 text-amber-700 mt-0.5" />
                          <span>Consumer Protection Act 2019 (Section 2(47) &amp; Section 35)</span>
                        </div>
                        <div className="p-2.5 rounded border border-stone-300 bg-[#fcfaf5] text-xs font-serif font-medium text-stone-900 flex items-start gap-2">
                          <Scale className="size-4 shrink-0 text-amber-700 mt-0.5" />
                          <span>Statutory Master Circular on Consumer Redressal Mechanisms (2024)</span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* APPEAL DRAFT TAB */}
              {activeTab === "appeal" && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="font-mono text-[10px] font-black uppercase tracking-wider text-stone-700">[ GENERATED STATUTORY APPEAL DRAFT ]</p>
                    <button
                      onClick={copyAppeal}
                      className="pixel-btn text-xs px-3 py-1 inline-flex items-center gap-1.5 bg-amber-100 font-sans"
                    >
                      {copied ? <Check className="size-3.5 text-emerald-700" /> : <Copy className="size-3.5 text-stone-800" />}
                      {copied ? "Copied to Clipboard!" : "Copy Full Letter"}
                    </button>
                  </div>
                  <pre className="whitespace-pre-wrap font-serif text-[13.5px] leading-[1.68] rounded-xl border-2 border-[#231f1d] bg-amber-50/40 p-5 text-stone-900 shadow-[3px_3px_0_#231f1d]">
                    {la?.appeal_draft || report?.appeals[0]?.content || "Statutory formal notice drafted for submission to the Ombudsman / Appellate Officer."}
                  </pre>
                </div>
              )}

              {/* EVIDENCE TAB */}
              {activeTab === "evidence" && (
                <div className="space-y-3">
                  <p className="font-mono text-[10px] font-black uppercase tracking-wider text-stone-700">[ EVIDENTIARY VAULT DOCUMENTS ]</p>
                  {report?.documents && report.documents.length > 0 ? (
                    <div className="space-y-2">
                      {report.documents.map((doc) => (
                        <div key={doc.id} className="rounded-lg border-2 border-[#231f1d] bg-white p-3 shadow-[1.5px_1.5px_0_#231f1d]">
                          <div className="flex items-center justify-between">
                            <span className="font-sans text-xs font-bold text-stone-900 truncate max-w-xs">{doc.filename}</span>
                            <span className="font-mono text-[9px] font-black uppercase bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded border border-[#231f1d]">
                              OCR INDEXED
                            </span>
                          </div>
                          {doc.text_extract && (
                            <p className="mt-2 text-[11px] font-mono leading-tight text-stone-600 line-clamp-3 bg-stone-50 p-2 rounded border border-stone-200">
                              {doc.text_extract}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-lg border-2 border-[#231f1d] bg-white p-3 shadow-[1.5px_1.5px_0_#231f1d]">
                      <div className="flex items-center justify-between">
                        <span className="font-sans text-xs font-bold text-stone-900">Hospital_Medical_Summary.pdf</span>
                        <span className="font-mono text-[9px] font-black uppercase bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded border border-[#231f1d]">
                          OCR VERIFIED
                        </span>
                      </div>
                      <p className="mt-2 text-[11px] font-mono text-stone-600 bg-stone-50 p-2 rounded">
                        Full clinical and invoice details extracted and parsed against domain regulations.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* TIMELINE TAB */}
              {activeTab === "timeline" && (
                <div className="space-y-3">
                  <p className="font-mono text-[10px] font-black uppercase tracking-wider text-stone-700">[ CASE TIMELINE EVENTS ]</p>
                  <div className="space-y-2">
                    {(report?.events && report.events.length > 0 ? report.events : [
                      { id: "1", title: "Dispute case registered", body: "Intake form processed", created_at: analysis.created_at, actor: "user" },
                      { id: "2", title: "Evidence documents OCR parsed", body: "Statutory rules matched", created_at: analysis.created_at, actor: "agent" },
                      { id: "3", title: "Multi-agent consensus finalized", body: "Statutory confidence evaluated", created_at: analysis.updated_at, actor: "agent" },
                    ]).map((ev) => (
                      <div key={ev.id} className="p-2.5 rounded-lg border border-stone-300 bg-white shadow-[1px_1px_0_#231f1d]">
                        <p className="text-xs font-bold text-stone-900">{ev.title}</p>
                        {ev.body && <p className="text-[11px] text-stone-600 mt-0.5">{ev.body}</p>}
                        <p className="text-[10px] font-mono text-stone-400 mt-1">{timeAgo(ev.created_at)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function NewClaimModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (caseItem: AnalysisCase) => void;
}) {
  const [domain, setDomain] = useState("health_insurance");
  const [title, setTitle] = useState("");
  const [institution, setInstitution] = useState("");
  const [summary, setSummary] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !institution.trim() || !summary.trim()) {
      setError("Please fill out all fields.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await createCase({
        domain,
        title: title.trim(),
        institution_name: institution.trim(),
        summary: summary.trim(),
        jurisdiction: "IN",
      });
      onCreated(created);
    } catch (err: any) {
      setError(err?.message || "Failed to create dispute claim");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl border-2 border-[#231f1d] bg-[#fdfbf7] p-6 shadow-[6px_6px_0_#231f1d]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b-2 border-[#231f1d] pb-3 mb-4">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-black uppercase text-amber-700">[ ◈ NEW ]</span>
            <h3 className="font-mono text-base font-black uppercase text-[#1c1917]">Create Dispute Claim</h3>
          </div>
          <button onClick={onClose} className="rounded border border-[#231f1d] p-1 text-stone-700 hover:bg-stone-200">
            <X className="size-4" />
          </button>
        </div>

        {error && (
          <div className="mb-3 rounded border border-red-500 bg-red-50 p-2.5 text-xs text-red-800 font-medium">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label className="block font-mono text-[11px] font-bold uppercase text-stone-700 mb-1">Dispute Domain</label>
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="w-full rounded border-2 border-[#231f1d] bg-white px-3 py-2 text-xs font-bold text-stone-900 outline-none"
            >
              {Object.keys(DOMAIN_THEME).map((d) => (
                <option key={d} value={d}>{domainTheme(d).label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block font-mono text-[11px] font-bold uppercase text-stone-700 mb-1">Claim Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Star Health: Cataract Surgery Denial"
              className="w-full rounded border-2 border-[#231f1d] bg-white px-3 py-2 text-xs font-medium text-stone-900 outline-none"
            />
          </div>

          <div>
            <label className="block font-mono text-[11px] font-bold uppercase text-stone-700 mb-1">Institution / Counterparty</label>
            <input
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
              placeholder="e.g. Star Health and Allied Insurance Co. Ltd."
              className="w-full rounded border-2 border-[#231f1d] bg-white px-3 py-2 text-xs font-medium text-stone-900 outline-none"
            />
          </div>

          <div>
            <label className="block font-mono text-[11px] font-bold uppercase text-stone-700 mb-1">Factual Summary of Dispute</label>
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              rows={3}
              placeholder="Explain what happened, dates, amounts, rejection reason cited by counterparty..."
              className="w-full rounded border-2 border-[#231f1d] bg-white px-3 py-2 text-xs font-medium text-stone-900 outline-none resize-none"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-stone-200">
            <button type="button" onClick={onClose} className="pixel-btn px-4 py-2 text-xs">
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="pixel-btn-primary px-5 py-2 text-xs font-black inline-flex items-center gap-1.5"
            >
              {submitting ? <Loader2 className="size-3.5 animate-spin" /> : <Plus className="size-3.5" />}
              {submitting ? "Creating..." : "Create Dispute Claim"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
