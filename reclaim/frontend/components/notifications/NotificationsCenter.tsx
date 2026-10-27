"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bell, Search, Loader2, PenLine, Upload, FileCheck2, ArrowUpCircle, Activity,
  CheckCheck, Radio, Download, ChevronDown, Bot,
} from "lucide-react";
import { getEvents, listAnalyses, type TimelineEvent, type AnalysisCase } from "@/lib/api-client";
import { domainTheme } from "@/components/chat/domain-theme";
import { PREF_KEYS, getPref } from "@/lib/preferences";

const EVENT_META: Record<string, { icon: typeof Activity; color: string; label: string }> = {
  case_created: { icon: PenLine, color: "#00e5ff", label: "Case created" },
  document_uploaded: { icon: Upload, color: "#37f29a", label: "Document uploaded" },
  appeal_drafted: { icon: FileCheck2, color: "#9b5cff", label: "Appeal drafted" },
  appeal_status_changed: { icon: ArrowUpCircle, color: "#ffc857", label: "Appeal status changed" },
  agent_run: { icon: Activity, color: "#ff6fb0", label: "Agent run" },
};

function eventMeta(type: string) {
  return EVENT_META[type] ?? { icon: Bell, color: "#a8b3c7", label: type };
}

function eventRoute(event: TimelineEvent): string {
  switch (event.event_type) {
    case "document_uploaded":
      return "/dashboard/documents";
    case "appeal_drafted":
    case "appeal_status_changed":
      return "/dashboard/appeals";
    case "case_created":
    case "agent_run":
      return `/dashboard/knowledge-graph?case=${encodeURIComponent(event.case_id)}`;
    default:
      return "/dashboard/analyses";
  }
}

function dayKey(iso: string | null): string {
  if (!iso) return "unknown";
  return new Date(iso).toDateString();
}

function groupLabel(iso: string | null): string {
  if (!iso) return "Earlier";
  const date = new Date(iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const eventDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((today.getTime() - eventDay.getTime()) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return "This week";
  return "Earlier";
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
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

const LAST_SEEN_KEY = "proxy:notifications-last-seen";
const HEATMAP_WEEKS = 10;

export function NotificationsCenter() {
  const router = useRouter();
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [domainFilter, setDomainFilter] = useState<string>("all");
  const [lastSeen, setLastSeen] = useState<string>("");
  // Initialize to the SSR-safe default and only read the real localStorage
  // value after mount -- reading it in the useState initializer runs during
  // both server and client render, and since localStorage only exists on
  // the client, a previously-saved "true" would make the client's first
  // render disagree with the server's, which React reports as a hydration
  // mismatch (and then throws away the whole server-rendered tree).
  const [live, setLive] = useState(false);
  useEffect(() => {
    setLive(getPref(PREF_KEYS.notificationsLive, "false") === "true");
  }, []);
  const [pulse, setPulse] = useState(false);
  const pollRef = useRef<number | null>(null);

  const domainByCaseId = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of analyses) map.set(a.id, a.domains_involved[0] ?? a.domain);
    return map;
  }, [analyses]);

  async function loadInitial() {
    setLoading(true);
    try {
      const [eventsResult, analysesResult] = await Promise.all([getEvents(40), listAnalyses()]);
      setEvents(eventsResult);
      setAnalyses(analysesResult);
      setHasMore(eventsResult.length === 40);
    } catch {
      // keep whatever we last had on a transient failure
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLastSeen(window.localStorage.getItem(LAST_SEEN_KEY) ?? new Date(0).toISOString());
    loadInitial();
  }, []);

  useEffect(() => {
    if (!live) {
      if (pollRef.current) window.clearInterval(pollRef.current);
      return;
    }
    pollRef.current = window.setInterval(async () => {
      try {
        const fresh = await getEvents(10);
        setEvents((current) => {
          const knownIds = new Set(current.map((e) => e.id));
          const newOnes = fresh.filter((e) => !knownIds.has(e.id));
          if (newOnes.length > 0) {
            setPulse(true);
            window.setTimeout(() => setPulse(false), 1200);
            return [...newOnes, ...current];
          }
          return current;
        });
      } catch {
        // transient failure -- keep polling
      }
    }, Number(getPref(PREF_KEYS.notificationsPollMs, "20000")));
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [live]);

  function toggleLive() {
    setLive((current) => {
      const next = !current;
      window.localStorage.setItem(PREF_KEYS.notificationsLive, String(next));
      return next;
    });
  }

  async function loadMore() {
    const oldest = events[events.length - 1];
    if (!oldest?.created_at) return;
    setLoadingMore(true);
    try {
      const more = await getEvents(30, oldest.created_at);
      setEvents((current) => [...current, ...more]);
      setHasMore(more.length === 30);
    } catch {
      // ignore
    } finally {
      setLoadingMore(false);
    }
  }

  function markAllRead() {
    const now = new Date().toISOString();
    setLastSeen(now);
    window.localStorage.setItem(LAST_SEEN_KEY, now);
  }

  function openEvent(event: TimelineEvent) {
    router.push(eventRoute(event));
  }

  function exportDigest() {
    const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `notifications-digest-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const filtered = useMemo(() => {
    return events.filter((e) => {
      if (typeFilter !== "all" && e.event_type !== typeFilter) return false;
      if (domainFilter !== "all" && domainByCaseId.get(e.case_id) !== domainFilter) return false;
      if (search && !`${e.title} ${e.body ?? ""}`.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [events, typeFilter, domainFilter, search, domainByCaseId]);

  const unreadCount = useMemo(() => events.filter((e) => (e.created_at ?? "") > lastSeen).length, [events, lastSeen]);

  const grouped = useMemo(() => {
    const groups = new Map<string, TimelineEvent[]>();
    for (const event of filtered) {
      const label = groupLabel(event.created_at);
      const list = groups.get(label) ?? [];
      list.push(event);
      groups.set(label, list);
    }
    return Array.from(groups.entries());
  }, [filtered]);

  const heatmap = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events) {
      if (!event.created_at) continue;
      const key = dayKey(event.created_at);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const days: Array<{ date: Date; count: number }> = [];
    const totalDays = HEATMAP_WEEKS * 7;
    for (let i = totalDays - 1; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      days.push({ date, count: counts.get(date.toDateString()) ?? 0 });
    }
    return days;
  }, [events]);

  const maxHeat = Math.max(1, ...heatmap.map((d) => d.count));
  const eventTypes = useMemo(() => Array.from(new Set(events.map((e) => e.event_type))), [events]);
  const involvedDomains = useMemo(() => Array.from(new Set(Array.from(domainByCaseId.values()))), [domainByCaseId]);

  return (
    <div className="flex min-h-[720px] flex-1 flex-col gap-4">
      {/* Hero: unread + live toggle + heatmap */}
      <section className="rounded-2xl border-2 border-[#231f1d] bg-white p-4 shadow-[4px_4px_0_#231f1d] sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="relative grid size-11 place-items-center rounded-xl border-2 border-[#231f1d] bg-amber-300 shadow-[2px_2px_0_#231f1d]">
              <Bell className="size-5 text-[#1c1917]" />
              {unreadCount > 0 && (
                <span className="absolute -right-2 -top-2 grid min-w-[20px] place-items-center rounded-full border-2 border-[#231f1d] bg-rose-500 px-1 text-[10px] font-black text-white shadow-[1px_1px_0_#231f1d]">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </div>
            <div>
              <p className="text-base font-black text-[#1c1917]">Live activity feed</p>
              <p className="text-xs font-medium text-stone-600">{unreadCount} unread &middot; {events.length} loaded</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={toggleLive}
              className={`inline-flex items-center gap-1.5 rounded-lg border-2 border-[#231f1d] px-3 py-1.5 text-xs font-bold shadow-[2px_2px_0_#231f1d] active:translate-x-0.5 active:translate-y-0.5 transition-all ${
                live ? "bg-emerald-300 text-emerald-950" : "bg-white text-stone-700 hover:bg-stone-50"
              }`}
            >
              <Radio className={`size-3.5 ${live ? "animate-pulse text-emerald-900" : "text-stone-500"}`} /> {live ? "Live polling on" : "Go live"}
            </button>
            <button
              onClick={markAllRead}
              className="inline-flex items-center gap-1.5 rounded-lg border-2 border-[#231f1d] bg-white px-3 py-1.5 text-xs font-bold text-stone-700 shadow-[2px_2px_0_#231f1d] hover:bg-stone-50 active:translate-x-0.5 active:translate-y-0.5"
            >
              <CheckCheck className="size-3.5" /> Mark all read
            </button>
            <button
              onClick={exportDigest}
              className="inline-flex items-center gap-1.5 rounded-lg border-2 border-[#231f1d] bg-white px-3 py-1.5 text-xs font-bold text-stone-700 shadow-[2px_2px_0_#231f1d] hover:bg-stone-50 active:translate-x-0.5 active:translate-y-0.5"
            >
              <Download className="size-3.5" /> Export digest
            </button>
          </div>
        </div>

        {/* Activity heatmap */}
        <div className={`overflow-x-auto rounded-xl border-2 border-[#231f1d] bg-[#fcfaf5] p-3 shadow-[2px_2px_0_#231f1d] transition-all ${pulse ? "ring-2 ring-amber-500" : ""}`}>
          <div className="mb-2 flex items-center justify-between font-mono text-[10px] font-bold uppercase tracking-wider text-stone-600">
            <span>Activity, last {HEATMAP_WEEKS} weeks</span>
            <span>{events.length} events logged</span>
          </div>
          <div className="grid grid-flow-col gap-1" style={{ gridTemplateRows: "repeat(7, 1fr)" }}>
            {heatmap.map((d, i) => {
              const intensity = d.count === 0 ? 0 : Math.min(1, d.count / maxHeat);
              return (
                <div
                  key={i}
                  title={`${d.date.toLocaleDateString()}: ${d.count} event${d.count === 1 ? "" : "s"}`}
                  className="size-3 rounded-sm border border-[#231f1d]/20"
                  style={{ backgroundColor: intensity === 0 ? "#ede8dc" : `rgba(217, 119, 6, ${0.25 + intensity * 0.75})` }}
                />
              );
            })}
          </div>
        </div>
      </section>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border-2 border-[#231f1d] bg-white p-3 shadow-[3px_3px_0_#231f1d]">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-stone-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search notifications..."
            className="w-full rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] py-2 pl-9 pr-3 text-xs font-semibold text-[#1c1917] outline-none placeholder:text-stone-400 focus:bg-white"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] px-3 py-2 text-xs font-bold text-[#1c1917] outline-none shadow-[2px_2px_0_#231f1d]"
        >
          <option value="all">All event types</option>
          {eventTypes.map((type) => (
            <option key={type} value={type}>
              {eventMeta(type).label}
            </option>
          ))}
        </select>
        {involvedDomains.length > 0 && (
          <select
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            className="rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] px-3 py-2 text-xs font-bold text-[#1c1917] outline-none shadow-[2px_2px_0_#231f1d]"
          >
            <option value="all">All domains</option>
            {involvedDomains.map((d) => (
              <option key={d} value={d}>
                {domainTheme(d).label}
              </option>
            ))}
          </select>
        )}
        <span className="ml-auto font-mono text-xs font-bold text-stone-600">{filtered.length} shown</span>
      </div>

      {/* Timeline */}
      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="size-6 animate-spin text-amber-700" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-[#231f1d]/30 bg-white p-6 text-center shadow-[2px_2px_0_#231f1d]">
          <Bell className="size-8 text-stone-400" />
          <p className="text-sm font-semibold text-stone-600">
            {events.length === 0
              ? "No activity recorded yet — ask the AI Assistant a question to get started."
              : "No notifications match your current filters."}
          </p>
          {events.length === 0 && (
            <button
              onClick={() => router.push("/dashboard/assistant")}
              className="inline-flex items-center gap-1.5 rounded-lg border-2 border-[#231f1d] bg-amber-300 px-3.5 py-2 text-xs font-black text-[#1c1917] shadow-[2px_2px_0_#231f1d] hover:bg-amber-400"
            >
              <Bot className="size-3.5" /> Ask the AI Assistant
            </button>
          )}
        </div>
      ) : (
        <div className="flex-1 space-y-5">
          {grouped.map(([label, items]) => (
            <div key={label}>
              <p className="mb-2 px-1 font-mono text-xs font-bold uppercase tracking-wider text-stone-600">{label}</p>
              <div className="space-y-2.5">
                {items.map((event) => {
                  const meta = eventMeta(event.event_type);
                  const Icon = meta.icon;
                  const unread = (event.created_at ?? "") > lastSeen;
                  const eventDomain = domainByCaseId.get(event.case_id);
                  return (
                    <button
                      key={event.id}
                      onClick={() => openEvent(event)}
                      className={`flex w-full items-start gap-3 rounded-xl border-2 border-[#231f1d] p-3.5 text-left transition-transform hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[4px_4px_0_#231f1d] ${
                        unread
                          ? "bg-amber-50 shadow-[3px_3px_0_#231f1d]"
                          : "bg-white shadow-[2px_2px_0_#231f1d]"
                      }`}
                    >
                      <div
                        className="relative mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg border-2 border-[#231f1d] shadow-[1px_1px_0_#231f1d]"
                        style={{ backgroundColor: `${meta.color}25` }}
                      >
                        <Icon className="size-4 text-[#1c1917]" />
                        {unread && (
                          <span className="absolute -right-1 -top-1 size-2.5 rounded-full border border-[#231f1d] bg-amber-500" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-black text-[#1c1917]">{event.title}</p>
                          {eventDomain && (
                            <span
                              className="shrink-0 rounded border border-[#231f1d] px-1.5 py-0.5 font-mono text-[9px] font-bold"
                              style={{
                                backgroundColor: `${domainTheme(eventDomain).color}22`,
                                color: "#1c1917",
                              }}
                            >
                              {domainTheme(eventDomain).label}
                            </span>
                          )}
                        </div>
                        {event.body && (
                          <p className="mt-1 line-clamp-1 text-xs font-medium text-stone-600">{event.body}</p>
                        )}
                        <p className="mt-1 font-mono text-[10px] text-stone-500">
                          {event.actor} &middot; {timeAgo(event.created_at)}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          {hasMore && (
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="mx-auto flex items-center gap-1.5 rounded-lg border-2 border-[#231f1d] bg-white px-4 py-2 text-xs font-bold text-[#1c1917] shadow-[2px_2px_0_#231f1d] hover:bg-amber-50"
            >
              {loadingMore ? <Loader2 className="size-3.5 animate-spin" /> : <ChevronDown className="size-3.5" />} Load more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
