"use client";

import { AppealsCenter } from "@/components/appeals/AppealsCenter";

export default function AppealsPage() {
  return (
    <div className="relative z-10 mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 py-5 sm:px-6 lg:px-8">
      <header className="mb-6">
        <span className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-700">
          [ ◈ STATUTORY RECOURSE &amp; APPEALS ]
        </span>
        <h1 className="mt-1 font-mono text-3xl sm:text-4xl font-black tracking-tight text-[#1c1917]">
          Consumer Appeals Center
        </h1>
        <p className="mt-2 max-w-3xl text-xs font-medium leading-5 text-stone-600">
          Every appeal letter, regulatory complaint email, escalation note, and statutory Ombudsman petition
          RESOLVE has generated for you — legally grounded with statutory citations (IRDAI, RERA, DGCA, RBI), ready to review and send.
        </p>
      </header>
      <AppealsCenter />
    </div>
  );
}
