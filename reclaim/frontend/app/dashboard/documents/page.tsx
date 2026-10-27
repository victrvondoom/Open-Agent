"use client";

import { DocumentVault } from "@/components/documents/DocumentVault";

export default function DocumentsPage() {
  return (
    <div className="relative z-10 mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 py-5 sm:px-6 lg:px-8">
      <header className="mb-6">
        <span className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-700">
          [ ◈ SECURE EVIDENCE REPOSITORY ]
        </span>
        <h1 className="mt-1 font-mono text-3xl sm:text-4xl font-black tracking-tight text-[#1c1917]">
          Document Vault
        </h1>
        <p className="mt-2 max-w-3xl text-xs font-medium leading-5 text-stone-600">
          End-to-end evidence ingestion, multi-page OCR parsing, policy clause classification, and vector indexing. Every uploaded bill, rejection letter, or policy contract becomes verifiable statutory evidence.
        </p>
      </header>
      <DocumentVault />
    </div>
  );
}
