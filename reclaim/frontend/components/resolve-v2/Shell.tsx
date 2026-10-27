"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bell, Bot, ClipboardList, Command, FileSearch, FileText, Gauge, Home, Network, Search, Settings, Upload, Workflow, X, ChevronRight, ScrollText, Loader2, ArrowUpRight, Building2, ShieldCheck, SlidersHorizontal, Scale,
} from "lucide-react";
import { listAnalyses, type AnalysisCase } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";
import { useLang } from "@/lib/i18n";
import { SceneBackground } from "@/components/3d/SceneBackground";

const nav = [
  ["Dashboard", "/dashboard", Home],
  ["Action Fabric", "/dashboard/connectors", ShieldCheck],
  ["Text Splitter", "/dashboard/text-splitter", SlidersHorizontal],
  ["Decision Engine", "/dashboard/decision-optimizer", Scale],
  ["New Claim", "/dashboard/new", Upload],
  ["My Analyses", "/dashboard/analyses", FileSearch],
  ["AI Assistant", "/dashboard/assistant", Bot],
  ["Knowledge Graph", "/dashboard/knowledge-graph", Network],
  ["Cross-Domain Search", "/dashboard/cross-domain-search", Search],
  ["Institution Radar", "/dashboard/institution-radar", Building2],
  ["Documents", "/dashboard/documents", FileText],
  ["Appeals", "/dashboard/appeals", ClipboardList],
  ["Reports", "/dashboard/reports", Gauge],
  ["Notifications", "/dashboard/notifications", Bell],
  ["Settings", "/dashboard/settings", Settings],
] as const;

function getDeviceId(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("resolve:device-user-id") ?? window.localStorage.getItem("proxy:device-user-id") ?? "";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { t } = useLang();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [deviceId, setDeviceId] = useState("");

  useEffect(() => setDeviceId(getDeviceId()), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <main className="min-h-screen bg-[#f7f4ec] text-[#1c1917]">
      <SceneBackground />
      <Aurora />
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:border-2 focus:border-[#231f1d] focus:bg-amber-300 focus:px-3 focus:py-2 focus:text-black focus:shadow-[3px_3px_0_#231f1d]">Skip to content</a>
      
      {/* Creamy White Pixel 3D Sidebar */}
      <aside className="fixed left-0 top-0 z-30 hidden h-screen w-72 border-r-2 border-[#231f1d] bg-[#fcfaf5] p-4 shadow-[3px_0px_0px_#231f1d] lg:block overflow-y-auto">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid size-11 place-items-center rounded-lg border-2 border-[#231f1d] bg-amber-300 shadow-[3px_3px_0_#231f1d]">
            <Workflow className="size-6 text-[#1c1917]" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <p className="font-serif text-2xl font-black tracking-tight text-[#1c1917]">RECLAIM</p>
              <span className="rounded border border-[#231f1d] bg-[#1c1917] px-1 py-0.5 text-[9px] font-black uppercase text-amber-200">OS</span>
            </div>
            <p className="font-mono text-[10px] font-bold text-amber-800">From problem to proof to resolution</p>
            <p className="font-serif italic text-[11px] text-stone-600">Universal Action Fabric</p>
            <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-[#231f1d] bg-[#fef3c7] px-2 py-0.5 text-[9px] font-mono font-extrabold text-[#92400e] shadow-[1.5px_1.5px_0_#231f1d]">
              <span>🏆</span> Built for Open Agent Hackathon
            </div>
          </div>
        </div>

        <nav className="space-y-1" aria-label="Primary navigation">
          {nav.map(([label, href, Icon]) => {
            const isActive = pathname === href || (href !== "/dashboard" && pathname?.startsWith(href));
            return (
              <Link
                key={label}
                href={href}
                className={`group flex items-center gap-3 rounded-lg border-2 px-3 py-2 text-xs font-bold font-sans transition-all ${
                  isActive
                    ? "border-[#231f1d] bg-amber-300 text-stone-900 shadow-[2px_2px_0_#231f1d]"
                    : "border-transparent text-stone-700 hover:border-[#231f1d] hover:bg-white hover:shadow-[2px_2px_0_#231f1d] focus-visible:bg-white"
                }`}
              >
                <Icon className={`size-4 ${isActive ? "text-stone-900" : "text-stone-600 group-hover:text-amber-700"}`} />
                {t(label)}
              </Link>
            );
          })}
        </nav>

        <Link
          href="/dashboard/new"
          className="mt-5 block rounded-lg border-2 border-[#231f1d] bg-white p-3.5 shadow-[3px_3px_0_#231f1d] transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0_#231f1d]"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-700">[ ◈ VOICE &amp; SOLVE ]</span>
            <ArrowUpRight className="size-3.5 text-stone-700" />
          </div>
          <p className="mt-1 font-serif text-sm font-bold text-[#1c1917]">Whisper &amp; solve dispute</p>
          <p className="mt-1 font-serif italic text-xs leading-relaxed text-stone-600">
            Voice Flow voice intake &middot; parallel multi-agent reasoning across 8 domains.
          </p>
        </Link>

        <div className="mt-6 flex items-center justify-between rounded-lg border-2 border-[#231f1d] bg-white p-2.5 shadow-[2px_2px_0_#231f1d]">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-emerald-600" />
              <p className="truncate font-mono text-xs font-bold text-stone-900">
                {deviceId ? deviceId.replace("device-", "").slice(0, 11) : "ACTIVE NODE"}
              </p>
            </div>
            <p className="text-[10px] font-medium text-stone-500">Local Device Identity</p>
          </div>
          <Link
            href="/dashboard/settings"
            aria-label="Open settings"
            className="shrink-0 rounded border-2 border-[#231f1d] bg-[#fcfaf5] p-1.5 text-stone-800 hover:bg-amber-100 shadow-[1px_1px_0_#231f1d]"
          >
            <Settings className="size-3.5" />
          </Link>
        </div>
      </aside>

      <section id="main" className="lg:pl-72 p-4 sm:p-6 lg:p-8">
        {/* Hackathon banner at top of main view */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border-2 border-[#231f1d] bg-[#fffbeb] px-4 py-2.5 shadow-[3px_3px_0_#231f1d]">
          <div className="flex items-center gap-2.5">
            <span className="rounded border border-[#231f1d] bg-amber-400 px-2 py-0.5 font-mono text-[10px] font-black uppercase text-[#1c1917] shadow-[1.5px_1.5px_0_#231f1d]">
              🏆 RECLAIM ACTION OS
            </span>
            <span className="text-xs font-bold text-stone-900">
              RECLAIM &mdash; From problem to proof to resolution &middot; Built for Open Agent Hackathon
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded border border-[#231f1d] bg-white px-2 py-0.5 font-mono text-[10px] font-bold text-amber-900 shadow-[1px_1px_0_#231f1d]">
              Action Fabric &times; Human Approval Gate
            </span>
          </div>
        </div>
        {children}
      </section>

      {/* Floating Pixel 3D Ctrl K button */}
      <button
        onClick={() => setPaletteOpen(true)}
        className="fixed bottom-4 right-4 z-40 inline-flex items-center gap-2 rounded-lg border-2 border-[#231f1d] bg-white px-3.5 py-2.5 text-xs font-black text-[#1c1917] shadow-[3px_3px_0_#231f1d] hover:bg-amber-100 transition-transform active:translate-x-0.5 active:translate-y-0.5"
      >
        <Command className="size-3.5 text-stone-800" /> Ctrl K
      </button>

      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} />}
    </main>
  );
}

function Aurora() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(#d5ccbc_1.5px,transparent_1.5px)] [background-size:20px_20px] opacity-40" />
    </div>
  );
}


function CommandPalette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listAnalyses()
      .then(setAnalyses)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const matchedAnalyses = useMemo(() => {
    if (!query.trim()) return analyses.slice(0, 5);
    const q = query.toLowerCase();
    return analyses.filter((a) => a.title.toLowerCase().includes(q) || a.institution_name.toLowerCase().includes(q)).slice(0, 6);
  }, [analyses, query]);

  const matchedNav = useMemo(() => {
    if (!query.trim()) return nav;
    const q = query.toLowerCase();
    return nav.filter(([label]) => label.toLowerCase().includes(q));
  }, [query]);

  function go(href: string) {
    router.push(href);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-start bg-black/40 px-4 pt-20 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="Global command palette" onClick={onClose}>
      <div className="mx-auto w-full max-w-2xl rounded-xl border-2 border-[#231f1d] bg-[#fbf9f2] p-4 shadow-[6px_6px_0_#231f1d]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b-2 border-[#231f1d] px-1 pb-3">
          <Search className="size-5 text-stone-800" />
          <input
            ref={inputRef}
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && query.trim() && go(`/dashboard/assistant?q=${encodeURIComponent(query.trim())}`)}
            placeholder="Search analyses, jump to a page, or ask the AI Assistant..."
            className="h-10 flex-1 bg-transparent text-sm font-medium outline-none placeholder:text-stone-500 text-stone-900"
          />
          <button onClick={onClose} aria-label="Close command palette" className="rounded-md border border-[#231f1d] p-1 text-stone-700 hover:bg-stone-200">
            <X className="size-4" />
          </button>
        </div>

        <div className="mt-3 max-h-[60vh] overflow-y-auto space-y-2">
          {query.trim() && (
            <button onClick={() => go(`/dashboard/assistant?q=${encodeURIComponent(query.trim())}`)} className="flex w-full items-center justify-between rounded-lg border-2 border-[#231f1d] bg-amber-100 px-3 py-2.5 text-left text-xs font-bold text-stone-900 hover:bg-amber-200 shadow-[2px_2px_0_#231f1d]">
              <span className="flex items-center gap-2"><Bot className="size-4 text-amber-700" /> Ask AI Assistant: &ldquo;{query.trim()}&rdquo;</span>
              <ArrowUpRight className="size-4" />
            </button>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-6 text-stone-500"><Loader2 className="size-4 animate-spin" /></div>
          ) : matchedAnalyses.length > 0 ? (
            <div>
              <p className="px-1 py-1 text-[10px] font-mono font-bold uppercase tracking-wide text-stone-500">{query.trim() ? "Matching analyses" : "Recent analyses"}</p>
              <div className="space-y-1">
                {matchedAnalyses.map((a) => (
                  <button
                    key={a.id}
                    onClick={() => go(`/dashboard/analyses?case=${encodeURIComponent(a.id)}`)}
                    className="flex w-full items-center justify-between gap-2 rounded-lg border border-stone-300 bg-white px-3 py-2 text-left text-xs font-semibold text-stone-800 hover:border-[#231f1d] hover:bg-amber-50 shadow-[1px_1px_0_#231f1d]"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <ScrollText className="size-3.5 shrink-0 text-amber-600" />
                      <span className="truncate">{a.title}</span>
                    </span>
                    <ChevronRight className="size-3.5 shrink-0 text-stone-500" />
                  </button>
                ))}
              </div>
            </div>
          ) : query.trim() ? (
            <p className="px-3 py-2 text-xs text-stone-500">No analyses match &ldquo;{query.trim()}&rdquo;.</p>
          ) : null}

          {matchedNav.length > 0 && (
            <div className="pt-2 border-t border-stone-300">
              <p className="px-1 py-1 text-[10px] font-mono font-bold uppercase tracking-wide text-stone-500">Pages</p>
              <div className="grid grid-cols-2 gap-1.5">
                {matchedNav.map(([label, href, Icon]) => (
                  <button key={label} onClick={() => go(href)} className="flex items-center justify-between rounded-md border border-stone-300 bg-white px-2.5 py-1.5 text-left text-xs font-semibold text-stone-800 hover:border-[#231f1d] hover:bg-stone-100 shadow-[1px_1px_0_#231f1d]">
                    <span className="flex items-center gap-1.5"><Icon className="size-3.5 text-stone-600" /> {label}</span>
                    <ChevronRight className="size-3 text-stone-400" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
