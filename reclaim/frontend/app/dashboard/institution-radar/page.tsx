"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, AlertTriangle, TrendingUp, Building2, ArrowUpRight, Search, Network } from "lucide-react";
import { getInstitutionRadar, type InstitutionRadarEntry } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";

export default function InstitutionRadarPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<InstitutionRadarEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getInstitutionRadar(25);
        if (!cancelled) setEntries(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load radar. Is the backend running?");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const maxCases = entries.length > 0 ? entries[0].total_cases : 1;
  const filtered = useMemo(
    () => entries.filter((e) => e.institution_name.toLowerCase().includes(search.toLowerCase())),
    [entries, search]
  );
  const totalDisputes = useMemo(() => entries.reduce((sum, e) => sum + e.total_cases, 0), [entries]);
  const domainsCovered = useMemo(() => new Set(entries.flatMap((e) => e.by_domain.map((d) => d.domain))).size, [entries]);

  function viewPatterns(entry: InstitutionRadarEntry) {
    const topDomain = [...entry.by_domain].sort((a, b) => b.case_count - a.case_count)[0]?.domain;
    if (!topDomain) return;
    router.push(`/dashboard/knowledge-graph?domain=${encodeURIComponent(topDomain)}&institution=${encodeURIComponent(entry.institution_name)}`);
  }

  return (
    <div className="relative z-10 mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-6">
        <span className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-700">
          [ ◈ ENTERPRISE ACCOUNTABILITY RADAR ]
        </span>
        <h1 className="mt-1 font-mono text-3xl sm:text-4xl font-black tracking-tight text-[#1c1917]">
          Institution Accountability Radar
        </h1>
        <p className="mt-2 max-w-2xl text-xs font-medium leading-5 text-stone-600">
          Real dispute volume per corporate or statutory institution, aggregated across all citizens and all 8 domains in the knowledge graph. Highlights systemic dispute patterns, unfulfilled turnaround times (TAT), and regulatory non-compliance.
        </p>
        {!loading && !error && entries.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-4 font-mono text-xs text-stone-600">
            <span className="rounded border border-[#231f1d] bg-white px-2 py-0.5 shadow-[1px_1px_0_#231f1d]">
              <strong className="text-stone-900">{entries.length}</strong> institutions tracked
            </span>
            <span className="rounded border border-[#231f1d] bg-white px-2 py-0.5 shadow-[1px_1px_0_#231f1d]">
              <strong className="text-stone-900">{totalDisputes}</strong> disputes on file
            </span>
            <span className="rounded border border-[#231f1d] bg-white px-2 py-0.5 shadow-[1px_1px_0_#231f1d]">
              <strong className="text-stone-900">{domainsCovered}</strong> domains active
            </span>
          </div>
        )}
      </header>

      {!loading && !error && entries.length > 0 && (
        <div className="relative mb-4 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-stone-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search institutions by name..."
            className="w-full rounded-lg border-2 border-[#231f1d] bg-white py-1.5 pl-8 pr-2 text-xs font-medium text-stone-900 outline-none shadow-[1.5px_1.5px_0_#231f1d] focus:border-amber-600 placeholder:text-stone-400"
          />
        </div>
      )}

      {loading && (
        <div className="rounded-xl border-2 border-[#231f1d] bg-white p-10 text-center shadow-[4px_4px_0_#231f1d]">
          <Loader2 className="mx-auto mb-3 size-6 animate-spin text-amber-600" />
          <p className="text-xs font-bold text-stone-900">Aggregating real case data across consumer domains...</p>
        </div>
      )}

      {error && !loading && (
        <div className="rounded-xl border-2 border-red-500 bg-red-50 p-4 text-xs font-bold text-red-800 shadow-[2px_2px_0_#231f1d]">{error}</div>
      )}

      {!loading && !error && entries.length === 0 && (
        <div className="rounded-xl border-2 border-dashed border-stone-300 bg-white p-10 text-center shadow-[2px_2px_0_#231f1d]">
          <Building2 className="mx-auto mb-3 size-8 text-stone-400" />
          <p className="font-mono text-xs font-bold text-stone-600">No institution patterns yet -- automatically populates as cases are analyzed.</p>
        </div>
      )}

      {!loading && !error && entries.length > 0 && filtered.length === 0 && (
        <div className="rounded-xl border-2 border-dashed border-stone-300 bg-white p-10 text-center shadow-[2px_2px_0_#231f1d]">
          <Search className="mx-auto mb-3 size-8 text-stone-400" />
          <p className="font-mono text-xs font-bold text-stone-600">No institution matches &quot;{search}&quot;.</p>
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="space-y-3">
          {filtered.map((entry) => (
            <InstitutionRow
              key={entry.institution_name}
              rank={entries.indexOf(entry) + 1}
              entry={entry}
              maxCases={maxCases}
              onAsk={() =>
                router.push(`/dashboard/assistant?q=${encodeURIComponent(`What patterns and statutory violations exist in disputes against ${entry.institution_name}?`)}`)
              }
              onViewPatterns={() => viewPatterns(entry)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function InstitutionRow({
  rank, entry, maxCases, onAsk, onViewPatterns,
}: {
  rank: number;
  entry: InstitutionRadarEntry;
  maxCases: number;
  onAsk: () => void;
  onViewPatterns: () => void;
}) {
  const widthPct = Math.max(4, Math.round((entry.total_cases / maxCases) * 100));
  const isHigh = rank <= 3;
  return (
    <div className="overflow-hidden rounded-xl border-2 border-[#231f1d] bg-white p-4 shadow-[3px_3px_0_#231f1d]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={`grid size-7 shrink-0 place-items-center rounded border-2 border-[#231f1d] font-mono text-xs font-black shadow-[1.5px_1.5px_0_#231f1d] ${
              isHigh ? "bg-amber-300 text-stone-900" : "bg-[#fcfaf5] text-stone-700"
            }`}
          >
            #{rank}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-black text-stone-900">{entry.institution_name}</p>
            <p className="font-mono text-[10px] text-stone-500">
              {entry.by_domain.length} domain{entry.by_domain.length === 1 ? "" : "s"} involved
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {isHigh && <AlertTriangle className="size-4 text-amber-600" />}
          <div className="text-right">
            <p className="font-mono text-xl font-black text-stone-900">{entry.total_cases}</p>
            <p className="font-mono text-[9px] uppercase text-stone-500">disputes on file</p>
          </div>
        </div>
      </div>

      <div className="mb-3 h-2 overflow-hidden rounded-full border border-[#231f1d] bg-stone-100">
        <div
          className="h-full transition-all"
          style={{ width: `${widthPct}%`, backgroundColor: isHigh ? "#f59e0b" : "#0284c7" }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {entry.by_domain.map((d) => {
          const theme = domainTheme(d.domain);
          return (
            <span
              key={d.domain}
              className="rounded border border-[#231f1d] bg-[#fcfaf5] px-2 py-0.5 text-[10px] font-mono font-bold shadow-[1px_1px_0_#231f1d]"
              style={{ color: theme.color }}
            >
              {theme.label} &middot; {d.case_count}
            </span>
          );
        })}
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={onViewPatterns}
            className="pixel-btn inline-flex items-center gap-1 px-2.5 py-1 text-[10px]"
          >
            <Network className="size-3" /> View graph <ArrowUpRight className="size-3" />
          </button>
          <button
            onClick={onAsk}
            className="pixel-btn-primary inline-flex items-center gap-1 px-2.5 py-1 text-[10px]"
          >
            <TrendingUp className="size-3" /> Ask Assistant <ArrowUpRight className="size-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
