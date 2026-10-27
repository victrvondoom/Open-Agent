"use client";

import { useEffect } from "react";
import { Bot } from "lucide-react";
import { KnowledgeGraphQueryProvider } from "./QueryProvider";
import { useKnowledgeGraphStore } from "./store";
import { ModeSwitcher } from "./components/ModeSwitcher";
import { AskAIPanel } from "./components/AskAIPanel";
import { ReasoningTrailMode } from "./modes/reasoning-trail/ReasoningTrailMode";
import { InstitutionMode } from "./modes/institution-intelligence/InstitutionMode";
import { FootprintMode } from "./modes/knowledge-footprint/FootprintMode";

function PageShell() {
  const mode = useKnowledgeGraphStore((s) => s.mode);
  const setMode = useKnowledgeGraphStore((s) => s.setMode);
  const setSelectedCaseId = useKnowledgeGraphStore((s) => s.setSelectedCaseId);
  const setPendingInstitutionQuery = useKnowledgeGraphStore((s) => s.setPendingInstitutionQuery);
  const askAIOpen = useKnowledgeGraphStore((s) => s.askAIOpen);
  const setAskAIOpen = useKnowledgeGraphStore((s) => s.setAskAIOpen);

  // Deep-link from Notifications / other pages (?case=<id>) straight into
  // that case's Reasoning Trail, or from the Institution Radar
  // (?institution=<domain>|<name>) straight into a pre-filled, auto-run
  // Institution Intelligence query.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const caseId = params.get("case");
    const domain = params.get("domain");
    const institution = params.get("institution");
    if (caseId) {
      setSelectedCaseId(caseId);
      setMode("reasoning-trail");
      window.history.replaceState({}, "", window.location.pathname);
    } else if (domain && institution) {
      setPendingInstitutionQuery({ domain, institution });
      setMode("institution-intelligence");
      window.history.replaceState({}, "", window.location.pathname);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openCase(caseId: string) {
    setSelectedCaseId(caseId);
    setMode("reasoning-trail");
  }

  return (
    <div className="flex min-h-[760px] flex-1 flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-2xl border-2 border-[#231f1d] bg-white p-5 shadow-[4px_4px_0_#231f1d] sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="font-mono text-xs font-black uppercase tracking-[.22em] text-amber-700">RESOLVE 3D Reasoning</p>
          <h1 className="mt-1 text-2xl font-black text-[#1c1917] sm:text-3xl">Knowledge Graph</h1>
          <p className="mt-1 max-w-2xl text-xs font-medium leading-5 text-stone-600">
            Interactive multi-case reasoning graph across institutions, statutory entities, and audit trails.
          </p>
        </div>
        <button
          onClick={() => setAskAIOpen(true)}
          className="inline-flex items-center gap-1.5 self-start rounded-lg border-2 border-[#231f1d] bg-amber-300 px-3.5 py-2 text-xs font-black text-[#1c1917] shadow-[2px_2px_0_#231f1d] hover:bg-amber-400 active:translate-x-0.5 active:translate-y-0.5 sm:self-auto"
        >
          <Bot className="size-3.5" /> Ask AI Assistant
        </button>
      </div>

      <ModeSwitcher />

      {mode === "reasoning-trail" && <ReasoningTrailMode />}
      {mode === "institution-intelligence" && <InstitutionMode />}
      {mode === "knowledge-footprint" && <FootprintMode onOpenCase={openCase} />}

      {askAIOpen && <AskAIPanel onClose={() => setAskAIOpen(false)} />}
    </div>
  );
}

/** Entry point for /dashboard/knowledge-graph. Everything under
 * features/knowledge-graph/ is self-contained: its own types, Zod schemas,
 * fetchers, TanStack Query client, Zustand store, and 3D scene logic. */
export function KnowledgeGraphPage() {
  return (
    <KnowledgeGraphQueryProvider>
      <PageShell />
    </KnowledgeGraphQueryProvider>
  );
}
