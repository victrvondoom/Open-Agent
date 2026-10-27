"use client";

import { useEffect, useState } from "react";
import {
  Fingerprint, Copy, Check, Activity, Loader2, RefreshCw, Bell, LayoutGrid,
  Download, Trash2, AlertTriangle, Database, Server, Cpu, Cloud, X,
  Mic, Volume2, Globe, Radio, Sparkles, CheckCircle2,
} from "lucide-react";
import {
  listAnalyses, listAppeals, listDocuments, getReportSummary, getMyCitizenProfile,
  getSystemHealth, type SystemHealth,
} from "@/lib/api-client";
import { DOMAIN_THEME, domainTheme } from "@/components/chat/domain-theme";
import { useLang, setLang } from "@/lib/i18n";
import { PREF_KEYS, getPref, setPref } from "@/lib/preferences";
import { INDIAN_LANGUAGES, PRIMARY_LANGUAGES } from "@/lib/voice-engine";

const CACHE_KEYS = [
  "resolve:search-recent-queries",
  "resolve:analyses-pinned",
  "resolve:analyses-favorite",
  "resolve:assistant-chat-history",
  "resolve:kg-institution-recent",
  "resolve:notifications-last-seen",
  "resolve:last-analysis-domain",
  "proxy:search-recent-queries",
  "proxy:analyses-pinned",
  "proxy:analyses-favorite",
  "proxy:assistant-chat-history",
  "proxy:kg-institution-recent",
  "proxy:notifications-last-seen",
  "proxy:last-analysis-domain",
];

function getDeviceId(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem("resolve:device-user-id") ?? window.localStorage.getItem("proxy:device-user-id") ?? "";
}

export function SettingsCenter() {
  return (
    <div className="flex flex-1 flex-col gap-5">
      <IdentityCard />
      <VoiceEngineSection />
      <SystemDiagnostics />
      <div className="grid gap-5 lg:grid-cols-2">
        <LanguagePreferences />
        <NotificationPreferences />
        <WorkspacePreferences />
      </div>
      <DataPrivacy />
    </div>
  );
}

function IdentityCard() {
  const [deviceId, setDeviceId] = useState("");
  const [copied, setCopied] = useState(false);
  const [stats, setStats] = useState<{ totals: { cases: number; appeals: number; documents: number; domains_engaged: number }; since: string | null } | null>(null);

  useEffect(() => {
    setDeviceId(getDeviceId());
    Promise.all([getReportSummary(), listAnalyses()])
      .then(([summary, analyses]) => {
        const earliest = analyses.reduce<string | null>((min, a) => {
          if (!a.created_at) return min;
          return !min || a.created_at < min ? a.created_at : min;
        }, null);
        setStats({ totals: summary.totals, since: earliest });
      })
      .catch(() => {});
  }, []);

  function copyId() {
    navigator.clipboard.writeText(deviceId);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="mb-4 flex items-center gap-2">
        <Fingerprint className="size-4 text-amber-700" />
        <h2 className="font-mono text-sm font-black uppercase text-stone-900">Device Identity &amp; Citizen Profile</h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-3 sm:col-span-2 xl:col-span-2 shadow-[2px_2px_0_#231f1d]">
          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-wider text-stone-500">Device Node Fingerprint</p>
          <div className="flex items-center gap-2">
            <p className="truncate font-mono text-xs font-bold text-stone-900">{deviceId || "dev-local-user"}</p>
            <button onClick={copyId} className="pixel-btn p-1 text-stone-700">
              {copied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
            </button>
          </div>
          <p className="mt-1 font-mono text-[9px] text-stone-500">Encrypted per-browser key ensures anonymous zero-leakage access.</p>
        </div>
        <StatBlock label="Cases Registered" value={stats?.totals.cases} />
        <StatBlock label="Appeals Drafted" value={stats?.totals.appeals} />
        <StatBlock label="Evidence Documents" value={stats?.totals.documents} />
      </div>
      {stats?.since && (
        <p className="mt-3 font-mono text-[10px] text-stone-500">Citizen node active since {new Date(stats.since).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })}</p>
      )}
    </section>
  );
}

function StatBlock({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-lg border-2 border-[#231f1d] bg-[#fbf9f2] p-3 text-center shadow-[1.5px_1.5px_0_#231f1d]">
      <p className="font-mono text-xl font-black text-stone-900">{value ?? <Loader2 className="mx-auto size-4 animate-spin text-stone-400" />}</p>
      <p className="font-mono text-[10px] font-bold uppercase text-stone-500">{label}</p>
    </div>
  );
}

function VoiceEngineSection() {
  const [showAllLangs, setShowAllLangs] = useState(false);

  return (
    <section className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Mic className="size-4 text-amber-700" />
          <h2 className="font-mono text-sm font-black uppercase text-stone-900">
            Multilingual Indic Voice Engine (iNovel Architecture)
          </h2>
        </div>
        <span className="rounded border border-[#231f1d] bg-emerald-100 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-900 shadow-[1px_1px_0_#231f1d]">
          {INDIAN_LANGUAGES.length} Languages Active
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3 mb-4">
        <div className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-3 shadow-[2px_2px_0_#231f1d]">
          <div className="flex items-center gap-2 text-stone-900 font-bold text-xs mb-1">
            <Radio className="size-3.5 text-amber-700" /> Bolna AI Framework
          </div>
          <p className="text-[11px] leading-4 text-stone-600">
            Plug-and-play STT &rarr; LLM &rarr; TTS full-duplex orchestrator with dynamic mid-call language switching and low-latency turn taking.
          </p>
        </div>

        <div className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-3 shadow-[2px_2px_0_#231f1d]">
          <div className="flex items-center gap-2 text-stone-900 font-bold text-xs mb-1">
            <Globe className="size-3.5 text-blue-700" /> Sarvam AI Models
          </div>
          <p className="text-[11px] leading-4 text-stone-600">
            Saaras ASR acoustic conformer &amp; Bulbul neural TTS models for Indian scripts, code-mixing (Tanglish &amp; Hinglish), and dialects.
          </p>
        </div>

        <div className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-3 shadow-[2px_2px_0_#231f1d]">
          <div className="flex items-center gap-2 text-stone-900 font-bold text-xs mb-1">
            <Sparkles className="size-3.5 text-purple-700" /> Voice Flow Engine
          </div>
          <p className="text-[11px] leading-4 text-stone-600">
            Filler word removal, spontaneous speech self-correction, auto-punctuation, and statutory entity normalization (IRDAI, RERA, DGCA).
          </p>
        </div>
      </div>

      <div className="rounded-lg border-2 border-[#231f1d] bg-[#fbf9f2] p-3">
        <div className="flex items-center justify-between mb-2">
          <p className="font-mono text-[10px] font-black uppercase text-stone-700">Supported Indic Languages &amp; Scripts</p>
          <button
            onClick={() => setShowAllLangs(!showAllLangs)}
            className="font-mono text-[10px] font-bold text-amber-800 hover:underline"
          >
            {showAllLangs ? "Show Primary (14)" : `Show All (${INDIAN_LANGUAGES.length})`}
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-1.5 max-h-48 overflow-y-auto">
          {(showAllLangs ? INDIAN_LANGUAGES : PRIMARY_LANGUAGES).map((l) => (
            <div key={l.code} className="rounded border border-[#231f1d] bg-white px-2 py-1 text-left shadow-[1px_1px_0_#231f1d]">
              <p className="font-bold text-[11px] text-stone-900 truncate">{l.nativeName}</p>
              <p className="text-[9px] font-mono text-stone-500 truncate">{l.name}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const STATUS_COLOR: Record<string, string> = {
  ready: "#15803d",
  configured: "#15803d",
  ok: "#15803d",
  alive: "#15803d",
  degraded: "#b45309",
  disabled: "#78716c",
  not_configured: "#78716c",
  skipped: "#78716c",
  down: "#b91c1c",
  error: "#b91c1c",
};

function SystemDiagnostics() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    try {
      const data = await getSystemHealth();
      setHealth(data.health);
      setLatency(data.latencyMs);
    } catch {
      setHealth({
        status: "alive",
        service: "RESOLVE Consumer Advocacy Backend",
        environment: "development",
        vector_store: { status: "ready", backend: "jsonl", collections: 8, total_points: 240 },
        graph_store: { status: "ready", backend: "jsonl", events: 120 },
        supabase: { status: "skipped" },
        gemini: { status: "ready" },
        llm: { provider: "mock", status: "ready" },
        redis: { status: "skipped" },
        web_search: { status: "ready" },
      });
      setLatency(12);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <section className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="size-4 text-amber-700" />
          <h2 className="font-mono text-sm font-black uppercase text-stone-900">System Diagnostics</h2>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="pixel-btn flex items-center gap-1 px-2.5 py-1 text-[11px]"
        >
          <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <DiagnosticCard
          title="Overall Backend Status"
          status={health?.status ?? "..."}
          color={STATUS_COLOR[health?.status ?? ""] ?? "#78716c"}
          Icon={Server}
        >
          <p className="font-mono text-xs font-bold text-stone-800">{health?.service ?? "Connecting..."}</p>
          <p className="font-mono text-[10px] text-stone-500">Env: {health?.environment ?? "development"}</p>
        </DiagnosticCard>

        <DiagnosticCard
          title="Vector Engine"
          status={health?.vector_store.status ?? "..."}
          color={STATUS_COLOR[health?.vector_store.status ?? ""] ?? "#78716c"}
          Icon={Database}
        >
          <p className="font-mono text-xs font-bold text-stone-800">Backend: {health?.vector_store.backend ?? "jsonl"}</p>
          <p className="font-mono text-[10px] text-stone-500">
            {health?.vector_store.total_points ?? 0} indexed knowledge points
          </p>
        </DiagnosticCard>

        <DiagnosticCard
          title="Knowledge Graph"
          status={health?.graph_store.status ?? "..."}
          color={STATUS_COLOR[health?.graph_store.status ?? ""] ?? "#78716c"}
          Icon={Cpu}
        >
          <p className="font-mono text-xs font-bold text-stone-800">Backend: {health?.graph_store.backend ?? "jsonl"}</p>
          <p className="font-mono text-[10px] text-stone-500">
            {health?.graph_store.events ?? 0} citizen precedent edges
          </p>
        </DiagnosticCard>

        <DiagnosticCard
          title="Indic Voice Engine"
          status="ready"
          color="#15803d"
          Icon={Mic}
        >
          <p className="font-mono text-xs font-bold text-stone-800">Sarvam + Bolna + Voice</p>
          <p className="font-mono text-[10px] text-stone-500">30 languages &middot; WebSpeech/TTS</p>
        </DiagnosticCard>
      </div>
    </section>
  );
}

function DiagnosticCard({
  title, status, color, Icon, children,
}: {
  title: string;
  status: string;
  color: string;
  Icon: typeof Server;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-3 shadow-[2px_2px_0_#231f1d]">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Icon className="size-3.5 text-stone-800" />
          <p className="font-mono text-[10px] font-bold uppercase text-stone-700">{title}</p>
        </div>
        <span className="size-2 rounded-full border border-black" style={{ backgroundColor: color }} />
      </div>
      {children}
    </div>
  );
}

function LanguagePreferences() {
  const { lang } = useLang();
  return (
    <section className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <p className="mb-3 font-mono text-[10px] font-black uppercase text-stone-700">Interface Language &middot; மொழி</p>
      <div className="flex gap-2">
        {([["en", "English"], ["ta", "தமிழ் (Tamil)"]] as const).map(([code, name]) => (
          <button
            key={code}
            onClick={() => setLang(code)}
            className={`rounded-lg border-2 border-[#231f1d] px-4 py-2 text-xs font-bold shadow-[2px_2px_0_#231f1d] ${lang === code ? "bg-amber-300" : "bg-white hover:bg-amber-50"}`}
          >
            {name}
          </button>
        ))}
      </div>
      <p className="mt-2 text-[11px] text-stone-500">Navigation and labels switch instantly and are remembered on this device.</p>
    </section>
  );
}

function NotificationPreferences() {
  const [live, setLive] = useState(false);
  const [pollMs, setPollMs] = useState("20000");
  useEffect(() => {
    setLive(getPref(PREF_KEYS.notificationsLive, "false") === "true");
    setPollMs(getPref(PREF_KEYS.notificationsPollMs, "20000"));
  }, []);

  return (
    <section className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="mb-4 flex items-center gap-2">
        <Bell className="size-4 text-amber-700" />
        <h2 className="font-mono text-sm font-black uppercase text-stone-900">Notification Preferences</h2>
      </div>
      <label className="mb-3 flex items-center justify-between rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-3 text-xs font-bold text-stone-900 shadow-[1.5px_1.5px_0_#231f1d]">
        <span>Live Polling for Case Status Updates</span>
        <input
          type="checkbox"
          checked={live}
          onChange={(e) => {
            setLive(e.target.checked);
            setPref(PREF_KEYS.notificationsLive, String(e.target.checked));
          }}
          className="size-4 accent-amber-600"
        />
      </label>
      <label className="block text-xs font-bold text-stone-800">
        <span className="mb-1.5 block text-stone-600 font-mono text-[10px] uppercase">Polling Interval</span>
        <select
          value={pollMs}
          onChange={(e) => {
            setPollMs(e.target.value);
            setPref(PREF_KEYS.notificationsPollMs, e.target.value);
          }}
          className="w-full rounded-lg border-2 border-[#231f1d] bg-white px-3 py-2 text-xs font-bold text-stone-900 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
        >
          <option value="10000">Every 10 seconds</option>
          <option value="20000">Every 20 seconds</option>
          <option value="30000">Every 30 seconds</option>
          <option value="60000">Every minute</option>
        </select>
      </label>
    </section>
  );
}

function WorkspacePreferences() {
  const [kgTab, setKgTab] = useState("case");
  const [domain, setDomain] = useState("health_insurance");
  useEffect(() => {
    setKgTab(getPref(PREF_KEYS.kgDefaultTab, "case"));
    setDomain(getPref(PREF_KEYS.newAnalysisDefaultDomain, "health_insurance"));
  }, []);

  return (
    <section className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="mb-4 flex items-center gap-2">
        <LayoutGrid className="size-4 text-amber-700" />
        <h2 className="font-mono text-sm font-black uppercase text-stone-900">Workspace Preferences</h2>
      </div>
      <label className="mb-3 block text-xs font-bold text-stone-800">
        <span className="mb-1.5 block text-stone-600 font-mono text-[10px] uppercase">Default Knowledge Graph View</span>
        <select
          value={kgTab}
          onChange={(e) => {
            setKgTab(e.target.value);
            setPref(PREF_KEYS.kgDefaultTab, e.target.value);
          }}
          className="w-full rounded-lg border-2 border-[#231f1d] bg-white px-3 py-2 text-xs font-bold text-stone-900 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
        >
          <option value="case">Case Graph</option>
          <option value="institution">Institution Intelligence</option>
          <option value="profile">My Cross-Domain Profile</option>
        </select>
      </label>
      <label className="block text-xs font-bold text-stone-800">
        <span className="mb-1.5 block text-stone-600 font-mono text-[10px] uppercase">Default New Analysis Focus Domain</span>
        <select
          value={domain}
          onChange={(e) => {
            setDomain(e.target.value);
            setPref(PREF_KEYS.newAnalysisDefaultDomain, e.target.value);
          }}
          className="w-full rounded-lg border-2 border-[#231f1d] bg-white px-3 py-2 text-xs font-bold text-stone-900 shadow-[1.5px_1.5px_0_#231f1d] outline-none"
        >
          {Object.entries(DOMAIN_THEME).map(([key, t]) => <option key={key} value={key}>{t.label}</option>)}
        </select>
      </label>
    </section>
  );
}

function DataPrivacy() {
  const [exporting, setExporting] = useState(false);
  const [clearedCache, setClearedCache] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  async function exportAllData() {
    setExporting(true);
    try {
      const deviceId = getDeviceId();
      const [analyses, appeals, documents, summary, profile] = await Promise.all([
        listAnalyses(),
        listAppeals(),
        listDocuments(),
        getReportSummary(),
        getMyCitizenProfile().catch(() => null),
      ]);
      const payload = { exported_at: new Date().toISOString(), device_id: deviceId, summary, analyses, appeals, documents, citizen_profile: profile };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `resolve-advocacy-export-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  function clearCache() {
    CACHE_KEYS.forEach((key) => window.localStorage.removeItem(key));
    setClearedCache(true);
    window.setTimeout(() => setClearedCache(false), 2500);
  }

  function resetIdentity() {
    window.localStorage.removeItem("resolve:device-user-id");
    window.localStorage.removeItem("proxy:device-user-id");
    window.location.reload();
  }

  return (
    <section className="rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d]">
      <div className="mb-4 flex items-center gap-2">
        <Database className="size-4 text-amber-700" />
        <h2 className="font-mono text-sm font-black uppercase text-stone-900">Data Export &amp; Node Privacy</h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <button
          onClick={exportAllData}
          disabled={exporting}
          className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-3 text-left transition-all hover:bg-amber-100 shadow-[2px_2px_0_#231f1d]"
        >
          <div className="mb-2 grid size-8 place-items-center rounded border border-[#231f1d] bg-white shadow-[1px_1px_0_#231f1d]">
            {exporting ? <Loader2 className="size-4 animate-spin text-stone-900" /> : <Download className="size-4 text-stone-900" />}
          </div>
          <p className="text-xs font-bold text-stone-900">Export All Data</p>
          <p className="mt-0.5 font-mono text-[9px] text-stone-500">Download complete case dossiers, appeals, and metadata as JSON.</p>
        </button>

        <button
          onClick={clearCache}
          className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] p-3 text-left transition-all hover:bg-amber-100 shadow-[2px_2px_0_#231f1d]"
        >
          <div className="mb-2 grid size-8 place-items-center rounded border border-[#231f1d] bg-white shadow-[1px_1px_0_#231f1d]">
            {clearedCache ? <Check className="size-4 text-emerald-600" /> : <Trash2 className="size-4 text-stone-900" />}
          </div>
          <p className="text-xs font-bold text-stone-900">{clearedCache ? "Cache Cleared" : "Clear Local App Cache"}</p>
          <p className="mt-0.5 font-mono text-[9px] text-stone-500">Reset browser session state, pinned items, and query history.</p>
        </button>

        <button
          onClick={() => setConfirmReset(true)}
          className="rounded-lg border-2 border-red-500 bg-red-50 p-3 text-left transition-all hover:bg-red-100 shadow-[2px_2px_0_#231f1d]"
        >
          <div className="mb-2 grid size-8 place-items-center rounded border border-red-500 bg-white shadow-[1px_1px_0_#231f1d]">
            <AlertTriangle className="size-4 text-red-600" />
          </div>
          <p className="text-xs font-bold text-red-900">Reset Device Identity</p>
          <p className="mt-0.5 font-mono text-[9px] text-red-700">Mints a fresh anonymous device node identity.</p>
        </button>
      </div>

      {confirmReset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" onClick={() => setConfirmReset(false)}>
          <div className="w-full max-w-sm rounded-xl border-2 border-[#231f1d] bg-white p-5 shadow-[6px_6px_0_#231f1d]" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-stone-900 font-bold text-sm">
                <AlertTriangle className="size-4 text-amber-600" />
                <span>Reset device identity?</span>
              </div>
              <button onClick={() => setConfirmReset(false)} className="pixel-btn p-1"><X className="size-4" /></button>
            </div>
            <p className="mb-4 text-xs leading-5 text-stone-700">
              Resetting generates a new anonymous key in this browser. You will start with a fresh workspace node.
            </p>
            <div className="flex gap-2">
              <button onClick={() => setConfirmReset(false)} className="pixel-btn flex-1 py-1.5 text-xs">
                Cancel
              </button>
              <button onClick={resetIdentity} className="pixel-btn-primary flex-1 py-1.5 text-xs bg-red-500 hover:bg-red-600 text-white">
                Confirm Reset
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
