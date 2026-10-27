"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Bot, Loader2, Send, X } from "lucide-react";
import { useKnowledgeGraphStore } from "../store";
import { askAboutCase } from "../api";

interface Exchange {
  question: string;
  answer: string;
}

/** "Ask the AI Assistant" cross-mode integration (spec 8). Slide-over chat
 * that queries the currently focused case; the answer becomes a caption and
 * the AI's cited node is focused in the scene, reusing the exact visual
 * language as Reasoning Replay. Scoped to whatever case is active in
 * Reasoning Trail mode -- if none is selected yet, it asks the user to pick
 * one first rather than answering with no graph context. */
export function AskAIPanel({ onClose }: { onClose: () => void }) {
  const selectedCaseId = useKnowledgeGraphStore((s) => s.selectedCaseId);
  const setMode = useKnowledgeGraphStore((s) => s.setMode);
  const setSelectedNodeId = useKnowledgeGraphStore((s) => s.setSelectedNodeId);
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<Exchange[]>([]);

  const mutation = useMutation({
    mutationFn: (q: string) => askAboutCase(selectedCaseId as string, q),
    onSuccess: (data, question) => {
      setHistory((h) => [...h, { question, answer: data.answer }]);
      setMessage("");
      // Cross-mode integration: bring the case graph into view with the
      // case node focused, so the chat answer and the graph feel like one
      // system rather than two disconnected panels (spec 8).
      setMode("reasoning-trail");
      setSelectedNodeId("case");
    },
  });

  function submit() {
    if (!message.trim() || !selectedCaseId || mutation.isPending) return;
    mutation.mutate(message.trim());
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l-2 border-[#231f1d] bg-[#fbf9f2] shadow-[-6px_0_0_#231f1d]">
      <div className="flex items-center justify-between border-b-2 border-[#231f1d] bg-white p-4">
        <div className="flex items-center gap-2">
          <Bot className="size-4 text-amber-700" />
          <p className="text-sm font-black text-[#1c1917]">Ask AI Assistant</p>
        </div>
        <button onClick={onClose} className="grid size-7 place-items-center rounded-lg border border-[#231f1d] text-stone-700 hover:bg-stone-200">
          <X className="size-4" />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {!selectedCaseId ? (
          <p className="text-xs font-medium text-stone-500">Select a case in Reasoning Trail mode first, then ask a natural-language question about it here.</p>
        ) : history.length === 0 ? (
          <p className="text-xs font-medium text-stone-500">Ask a question about the current case — e.g. &quot;Why did this claim get denied?&quot;</p>
        ) : (
          history.map((ex, i) => (
            <div key={i} className="space-y-2">
              <p className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-xs font-bold text-[#1c1917] shadow-[1px_1px_0_#231f1d]">{ex.question}</p>
              <p className="rounded-lg border-2 border-[#231f1d] bg-amber-50 px-3 py-2 text-xs font-medium leading-5 text-stone-800 shadow-[2px_2px_0_#231f1d]">{ex.answer}</p>
            </div>
          ))
        )}
        {mutation.isError && <p className="text-xs font-bold text-rose-600">{(mutation.error as Error).message}</p>}
      </div>

      <div className="flex items-center gap-2 border-t-2 border-[#231f1d] bg-white p-3">
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          disabled={!selectedCaseId}
          placeholder={selectedCaseId ? "Ask about this case..." : "Select a case first..."}
          className="flex-1 rounded-lg border-2 border-[#231f1d] bg-[#fcfaf5] px-3 py-2 text-xs font-semibold text-[#1c1917] outline-none placeholder:text-stone-400 focus:bg-white disabled:opacity-40"
        />
        <button
          onClick={submit}
          disabled={!selectedCaseId || !message.trim() || mutation.isPending}
          className="grid size-9 shrink-0 place-items-center rounded-lg border-2 border-[#231f1d] bg-amber-300 text-[#1c1917] shadow-[2px_2px_0_#231f1d] hover:bg-amber-400 disabled:opacity-30 active:translate-x-0.5 active:translate-y-0.5"
        >
          {mutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        </button>
      </div>
    </div>
  );
}
