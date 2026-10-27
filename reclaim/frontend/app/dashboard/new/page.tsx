import { NewAnalysisFlow } from "@/components/new-analysis/NewAnalysisFlow";

export default function Page() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[.22em] text-cyan-200">RESOLVE &middot; VOICE &amp; SOLVE</p>
          <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Whisper &amp; Solve: Multi-Domain AI Analysis</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-proxy-muted">
            Whisper and solve using Voice Flow: speak or dictate your grievance freely, attach evidence, and watch our multi-agent legal engine synthesize statutory claims in real time.
          </p>
        </div>
      </header>
      <NewAnalysisFlow />
    </div>
  );
}
