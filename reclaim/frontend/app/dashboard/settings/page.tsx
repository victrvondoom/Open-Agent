import { SettingsCenter } from "@/components/settings/SettingsCenter";

export default function Page() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-6">
        <span className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-700">
          [ ◈ SYSTEM CONFIGURATION &amp; PREFERENCES ]
        </span>
        <h1 className="mt-1 font-mono text-3xl sm:text-4xl font-black tracking-tight text-[#1c1917]">
          Settings &amp; Diagnostics
        </h1>
        <p className="mt-2 max-w-3xl text-xs font-medium leading-5 text-stone-600">
          Local device identity, live system diagnostics, Indic voice engine settings, and preferences for notifications and knowledge graph visualization.
        </p>
      </header>
      <SettingsCenter />
    </div>
  );
}
