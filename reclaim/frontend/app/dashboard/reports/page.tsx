"use client";

import { ReportsDashboard } from "@/components/reports/ReportsDashboard";

export default function ReportsPage() {
  return (
    <div className="relative z-10 mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 py-5 sm:px-6 lg:px-8">
      <header className="mb-6">
        <span className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-700">
          [ ◈ ADVOCACY PERFORMANCE METRICS ]
        </span>
        <h1 className="mt-1 font-mono text-3xl sm:text-4xl font-black tracking-tight text-[#1c1917]">
          Advocacy Reports &amp; Analytics
        </h1>
        <p className="mt-2 max-w-3xl text-xs font-medium leading-5 text-stone-600">
          Real-time metrics from your dispute cases, generated statutory appeals, and indexed evidence documents — with exportable audit logs and printable case dossiers.
        </p>
      </header>
      <ReportsDashboard />
    </div>
  );
}
