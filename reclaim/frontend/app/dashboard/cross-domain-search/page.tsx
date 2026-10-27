"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search, Loader2, ExternalLink, ShieldCheck, Sparkles, Command, Clock, X,
  ChevronDown, ChevronUp, MessageSquare, Zap, Layers, Gauge,
} from "lucide-react";
import { classifyQuery, globalSearch, type DomainCandidate, type GlobalSearchResult } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";
import { EvidenceScoreBreakdown } from "@/components/search/EvidenceScoreBreakdown";
import { VoiceAssistant } from "@/components/chat/VoiceAssistant";

const RECENT_KEY = "proxy:search-recent-queries";
const SORT_OPTIONS = [
  { key: "evidence", label: "Evidence score" },
  { key: "domain", label: "Domain" },
] as const;
type SortKey = (typeof SORT_OPTIONS)[number]["key"];

function loadRecent(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveRecent(query: string) {
  const current = loadRecent().filter((q) => q !== query);
  current.unshift(query);
  window.localStorage.setItem(RECENT_KEY, JSON.stringify(current.slice(0, 8)));
}

export default function CrossDomainSearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [livePreview, setLivePreview] = useState<DomainCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<DomainCandidate[]>([]);
  const [results, setResults] = useState<GlobalSearchResult[]>([]);
  const [domainsSearched, setDomainsSearched] = useState<string[]>([]);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<string>("all");
  const [sortKey, setSortKey] = useState<SortKey>("evidence");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const [showRecent, setShowRecent] = useState(false);
  const [loadingElapsedMs, setLoadingElapsedMs] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setRecent(loadRecent()), []);

  useEffect(() => {
    if (!loading) {
      setLoadingElapsedMs(0);
      return;
    }
    const start = performance.now();
    const timer = window.setInterval(() => setLoadingElapsedMs(Math.round(performance.now() - start)), 200);
    return () => window.clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    function onKeydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, []);

  useEffect(() => {
    if (query.trim().length < 12) {
      setLivePreview([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        setLivePreview((await classifyQuery(query)).candidates);
      } catch {
        setLivePreview([]);
      }
    }, 450);
    return () => window.clearTimeout(timer);
  }, [query]);

  async function runSearch(overrideQuery?: string) {
    const q = (overrideQuery ?? query).trim();
    if (!q) return;
    setQuery(q);
    setShowRecent(false);
    setLoading(true);
    setError(null);
    setActiveTab("all");
    const start = performance.now();
    try {
      const [classification, search] = await Promise.all([classifyQuery(q), globalSearch(q)]);
      setCandidates(classification.candidates);
      setResults(search.results);
      setDomainsSearched(search.domains_searched);
      setElapsedMs(Math.round(performance.now() - start));
      saveRecent(q);
      setRecent(loadRecent());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed. Is the backend running?");
      setCandidates([]);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  const domainTabs = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of results) counts.set(r.domain, (counts.get(r.domain) ?? 0) + 1);
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [results]);

  const visibleResults = useMemo(() => {
    let filtered = activeTab === "all" ? results : results.filter((r) => r.domain === activeTab);
    filtered = [...filtered];
    if (sortKey === "evidence") {
      filtered.sort((a, b) => b.evidence_scores.overall_evidence_score - a.evidence_scores.overall_evidence_score);
    } else {
      filtered.sort((a, b) => a.domain.localeCompare(b.domain));
    }
    return filtered;
  }, [results, activeTab, sortKey]);

  const avgConfidence = useMemo(() => {
    if (results.length === 0) return 0;
    return results.reduce((sum, r) => sum + r.evidence_scores.overall_evidence_score, 0) / results.length;
  }, [results]);

  function askAboutQuery(q: string) {
    router.push(`/dashboard/assistant?q=${encodeURIComponent(q)}`);
  }

  return (
    <div className="relative z-10 mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-6">
        <span className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-700">
          [ ◈ CROSS-DOMAIN STATUTORY SEARCH ]
        </span>
        <h1 className="mt-1 font-mono text-3xl sm:text-4xl font-black tracking-tight text-[#1c1917]">
          Cross-Domain Search
        </h1>
        <p className="mt-1 text-xs font-medium text-stone-600">
          Query statutory precedents, regulations, and case decisions across all 8 consumer protection domains simultaneously — with multilingual voice input in 30 Indian languages.
        </p>
      </header>

      {/* Search composer */}
      <div className="relative mb-6">
        <div className="flex items-center gap-2 rounded-xl border-2 border-[#231f1d] bg-white p-2 shadow-[4px_4px_0_#231f1d]">
          <Search className="ml-2 size-4 shrink-0 text-stone-500" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onFocus={() => setShowRecent(true)}
            onBlur={() => window.setTimeout(() => setShowRecent(false), 150)}
            onKeyDown={(event) => event.key === "Enter" && runSearch()}
            placeholder="Speak or type: e.g. Flight cancelled and travel insurance rejected claim... (Ctrl/Cmd+K)"
            className="flex-1 bg-transparent px-1 py-1.5 text-xs font-medium text-stone-900 outline-none placeholder:text-stone-400"
          />
          {query && (
            <button onClick={() => setQuery("")} className="pixel-btn p-1 text-stone-500 hover:text-stone-900">
              <X className="size-3" />
            </button>
          )}

          {/* Multilingual Voice Assistant Button */}
          <VoiceAssistant compact onTranscript={(text) => {
            const next = query ? `${query} ${text}` : text;
            setQuery(next);
            runSearch(next);
          }} />

          <button
            onClick={() => runSearch()}
            disabled={loading || !query.trim()}
            className="pixel-btn-primary inline-flex items-center gap-1.5 px-4 py-2 text-xs uppercase tracking-wide disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
            {loading ? "Searching" : "Search"}
          </button>
        </div>

        {livePreview.length > 0 && !loading && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 px-1">
            <span className="font-mono text-[10px] font-bold uppercase tracking-wide text-stone-500">Detected:</span>
            {livePreview.map((c) => {
              const theme = domainTheme(c.domain);
              return (
                <span key={c.domain} className="rounded border border-[#231f1d] bg-white px-2 py-0.5 text-[10px] font-mono font-bold shadow-[1px_1px_0_#231f1d]" style={{ color: theme.color }}>
                  {theme.label} ({Math.round(c.confidence * 100)}%)
                </span>
              );
            })}
          </div>
        )}

        {showRecent && recent.length > 0 && (
          <div className="absolute left-0 right-0 top-full z-20 mt-2 rounded-xl border-2 border-[#231f1d] bg-white p-2 shadow-[4px_4px_0_#231f1d]">
            <p className="mb-1.5 flex items-center gap-1.5 px-2 font-mono text-[10px] font-black uppercase text-stone-600">
              <Clock className="size-3 text-amber-700" /> Recent queries
            </p>
            {recent.map((q) => (
              <button
                key={q}
                onMouseDown={() => runSearch(q)}
                className="block w-full truncate rounded-lg px-2 py-1.5 text-left text-xs font-medium text-stone-800 hover:bg-amber-100"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="mb-6 rounded-xl border-2 border-red-500 bg-red-50 p-4 text-xs font-bold text-red-800 shadow-[2px_2px_0_#231f1d]">{error}</div>
      )}

      {loading && <SearchingPanel elapsedMs={loadingElapsedMs} candidates={livePreview.length > 0 ? livePreview : candidates} />}

      {results.length > 0 && !loading && (
        <>
          {/* Stats bar */}
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatChip icon={Layers} label="Results" value={String(results.length)} />
            <StatChip icon={ShieldCheck} label="Domains" value={String(domainsSearched.length)} />
            <StatChip icon={Gauge} label="Avg. evidence" value={`${Math.round(avgConfidence * 100)}%`} />
            <StatChip icon={Zap} label="Search time" value={elapsedMs !== null ? `${elapsedMs}ms` : "-"} />
          </div>

          {/* Domain tabs */}
          <div className="mb-4 flex flex-wrap items-center gap-1.5">
            <TabChip label="All" count={results.length} active={activeTab === "all"} onClick={() => setActiveTab("all")} />
            {domainTabs.map(([domain, count]) => {
              const theme = domainTheme(domain);
              return (
                <TabChip
                  key={domain}
                  label={theme.label}
                  count={count}
                  active={activeTab === domain}
                  color={theme.color}
                  onClick={() => setActiveTab(domain)}
                />
              );
            })}
            <div className="ml-auto flex items-center gap-1.5">
              <span className="font-mono text-[10px] font-bold text-stone-500">Sort:</span>
              {SORT_OPTIONS.map((opt) => (
                <button
                  key={opt.key}
                  onClick={() => setSortKey(opt.key)}
                  className={`rounded border-2 border-[#231f1d] px-2.5 py-1 text-[10px] font-mono font-bold transition-all shadow-[1.5px_1.5px_0_#231f1d] ${
                    sortKey === opt.key ? "bg-amber-300 text-stone-900" : "bg-white text-stone-700 hover:bg-stone-50"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Ask AI CTA */}
          <button
            onClick={() => askAboutQuery(query)}
            className="pixel-btn mb-4 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-amber-900 bg-amber-50"
          >
            <MessageSquare className="size-3.5" /> Ask AI Assistant to reason about this with multi-agent pipeline &rarr;
          </button>

          {/* Results */}
          <div className="space-y-3">
            {visibleResults.map((result) => (
              <ResultCard
                key={result.id}
                result={result}
                expanded={expandedId === result.id}
                onToggle={() => setExpandedId(expandedId === result.id ? null : result.id)}
              />
            ))}
          </div>
        </>
      )}

      {!loading && !error && results.length === 0 && (
        <EmptyState onPick={(q) => runSearch(q)} />
      )}
    </div>
  );
}

function SearchingPanel({ elapsedMs, candidates }: { elapsedMs: number; candidates: DomainCandidate[] }) {
  const seconds = (elapsedMs / 1000).toFixed(1);
  return (
    <div className="mb-6 rounded-xl border-2 border-[#231f1d] bg-white p-6 text-center shadow-[4px_4px_0_#231f1d]">
      <Loader2 className="mx-auto mb-3 size-6 animate-spin text-amber-600" />
      <p className="text-xs font-bold text-stone-900">Searching across 8 consumer protection domains and vector knowledge graph...</p>
      <p className="mt-1 font-mono text-[10px] text-stone-500">{seconds}s elapsed &middot; retrieving statutory authorities and evidence grounding</p>
      {candidates.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5">
          <span className="font-mono text-[10px] font-bold uppercase text-stone-500">Most relevant:</span>
          {candidates.map((c) => {
            const theme = domainTheme(c.domain);
            return (
              <span key={c.domain} className="rounded border border-[#231f1d] bg-[#fcfaf5] px-2 py-0.5 text-[10px] font-mono font-bold shadow-[1px_1px_0_#231f1d]" style={{ color: theme.color }}>
                {theme.label}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StatChip({ icon: Icon, label, value }: { icon: typeof Layers; label: string; value: string }) {
  return (
    <div className="rounded-xl border-2 border-[#231f1d] bg-white p-3 shadow-[2.5px_2.5px_0_#231f1d]">
      <div className="mb-1 flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase text-stone-500">
        <Icon className="size-3 text-stone-800" /> {label}
      </div>
      <p className="font-mono text-xl font-black text-stone-900">{value}</p>
    </div>
  );
}

function TabChip({ label, count, active, onClick, color }: { label: string; count: number; active: boolean; onClick: () => void; color?: string }) {
  return (
    <button
      onClick={onClick}
      className={`rounded border-2 border-[#231f1d] px-3 py-1 text-xs font-mono font-bold transition-all shadow-[1.5px_1.5px_0_#231f1d] ${
        active ? "bg-amber-300 text-stone-900" : "bg-white text-stone-700 hover:bg-stone-50"
      }`}
    >
      {label} <span className="opacity-70 font-sans">({count})</span>
    </button>
  );
}

function ResultCard({ result, expanded, onToggle }: { result: GlobalSearchResult; expanded: boolean; onToggle: () => void }) {
  const theme = domainTheme(result.domain);
  const authority = typeof result.metadata.authority === "string" ? result.metadata.authority : null;
  const sourceUrl = typeof result.metadata.source_url === "string" ? result.metadata.source_url : null;

  return (
    <div
      className="overflow-hidden rounded-xl border-2 border-[#231f1d] bg-white shadow-[3px_3px_0_#231f1d] transition-all"
      style={{ borderLeftColor: theme.color, borderLeftWidth: 4 }}
    >
      <div className="p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="rounded border border-[#231f1d] px-2 py-0.5 text-[10px] font-mono font-bold shadow-[1px_1px_0_#231f1d]" style={{ backgroundColor: "#fcfaf5", color: theme.color }}>
            {theme.label}
          </span>
          {authority && (
            <span className="inline-flex items-center gap-1 rounded border border-stone-300 bg-stone-50 px-2 py-0.5 text-[10px] font-mono font-bold text-stone-700">
              <ShieldCheck className="size-3 text-emerald-600" /> {authority}
            </span>
          )}
          <button
            onClick={onToggle}
            className="pixel-btn ml-auto flex items-center gap-1 px-2 py-0.5 text-[10px]"
          >
            {Math.round(result.evidence_scores.overall_evidence_score * 100)}% evidence
            {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
          </button>
        </div>
        <p className={`text-xs leading-5 text-stone-800 ${expanded ? "" : "line-clamp-3"}`}>{result.text}</p>
        {sourceUrl && (
          <a href={sourceUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 font-mono text-[10px] font-bold text-amber-800 hover:underline">
            View Source Statutory Record <ExternalLink className="size-3" />
          </a>
        )}
      </div>
      {expanded && (
        <div className="border-t-2 border-stone-200 bg-[#fbf9f2] p-4">
          <p className="mb-2 font-mono text-[10px] font-black uppercase tracking-wider text-stone-700">Evidence Quality &amp; Ranking Score</p>
          <EvidenceScoreBreakdown scores={result.evidence_scores} />
        </div>
      )}
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  const suggestions = [
    "IndiGo flight cancelled 2 hours before departure and compensation refused under DGCA CAR",
    "Builder delayed flat possession by 18 months under RERA Section 18",
    "HDFC bank charged duplicate UPI transaction of ₹5000 and refused reversal",
    "Star Health denied insurance claim for pre-existing disease under IRDAI guidelines",
  ];
  return (
    <div className="rounded-xl border-2 border-dashed border-stone-300 bg-white p-8 text-center shadow-[2px_2px_0_#231f1d]">
      <Command className="mx-auto mb-3 size-8 text-stone-400" />
      <p className="mb-3 font-mono text-xs font-bold uppercase text-stone-700">
        Try cross-domain queries spanning multiple regulatory bodies
      </p>
      <div className="mx-auto grid max-w-2xl gap-2 sm:grid-cols-2">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-2.5 text-left text-xs font-medium text-stone-800 transition-all hover:bg-amber-100 shadow-[1.5px_1.5px_0_#231f1d]"
          >
            &ldquo;{s}&rdquo;
          </button>
        ))}
      </div>
    </div>
  );
}
