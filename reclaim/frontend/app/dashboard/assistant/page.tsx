"use client";

import { AssistantChat } from "@/components/chat/AssistantChat";
import { VoiceAssistant } from "@/components/chat/VoiceAssistant";
import { INDIAN_LANGUAGES } from "@/lib/voice-engine";

export default function AssistantPage() {
  return (
    <div className="relative z-10 mx-auto flex h-[calc(100dvh-5rem)] max-w-[1600px] flex-col px-4 py-5 sm:px-6 lg:px-8">
      <header className="mb-4 shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-black uppercase text-amber-700">[ ◈ COMMAND CENTER ]</span>
        </div>
        <h1 className="mt-2 text-2xl sm:text-3xl font-black uppercase tracking-tight text-[#1c1917] font-mono">
          AI Legal Assistant
        </h1>
        <p className="mt-1 max-w-3xl text-xs sm:text-sm font-medium text-stone-600">
          Multi-agent assistant with {INDIAN_LANGUAGES.length}-language voice support &middot; classifies your question across all 8 domains &middot; retrieves real evidence
        </p>
      </header>
      <AssistantChat />
    </div>
  );
}
