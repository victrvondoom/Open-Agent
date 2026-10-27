"use client";

import { Landmark, Orbit, Waypoints } from "lucide-react";
import { useKnowledgeGraphStore, type KGMode } from "../store";

const MODES: Array<{ id: KGMode; label: string; icon: typeof Waypoints }> = [
  { id: "reasoning-trail", label: "Reasoning Trail", icon: Waypoints },
  { id: "institution-intelligence", label: "Institution Intelligence", icon: Landmark },
  { id: "knowledge-footprint", label: "My Knowledge Footprint", icon: Orbit },
];

/** Three-way pill switcher (spec 2) -- three genuinely different visual
 * experiences, not tabs on one graph. Active mode gets the signature accent
 * glow. */
export function ModeSwitcher() {
  const mode = useKnowledgeGraphStore((s) => s.mode);
  const setMode = useKnowledgeGraphStore((s) => s.setMode);

  return (
    <div className="flex flex-wrap items-center gap-2 overflow-x-auto rounded-xl border-2 border-[#231f1d] bg-white p-2 shadow-[3px_3px_0_#231f1d]">
      {MODES.map((m) => {
        const active = mode === m.id;
        return (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            className={`inline-flex shrink-0 items-center gap-2 rounded-lg border-2 px-3.5 py-2 text-xs font-bold transition-transform active:translate-x-0.5 active:translate-y-0.5 ${
              active
                ? "border-[#231f1d] bg-amber-300 text-[#1c1917] shadow-[2px_2px_0_#231f1d]"
                : "border-transparent text-stone-700 hover:border-[#231f1d] hover:bg-[#f7f4ec]"
            }`}
          >
            <m.icon className="size-4" /> {m.label}
          </button>
        );
      })}
    </div>
  );
}
