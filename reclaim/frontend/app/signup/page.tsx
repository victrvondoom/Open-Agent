"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Workflow, ArrowRight, ShieldCheck, Loader2 } from "lucide-react";

export default function SignupPage() {
  const router = useRouter();

  useEffect(() => {
    // Instant direct access to dashboard -- no signup needed
    const timer = setTimeout(() => {
      router.replace("/dashboard");
    }, 150);
    return () => clearTimeout(timer);
  }, [router]);

  return (
    <main className="grid min-h-screen place-items-center bg-[#f7f4ec] px-4 text-[#1a1715]">
      <section className="w-full max-w-md rounded-2xl border-2 border-[#231f1d] bg-[#ffffff] p-8 shadow-[5px_5px_0px_#231f1d]">
        <div className="mb-6 flex items-center gap-4">
          <div className="grid size-12 place-items-center rounded-xl border-2 border-[#231f1d] bg-amber-300 text-[#1a1715] shadow-[2px_2px_0px_#231f1d]">
            <Workflow className="size-6 animate-pulse" />
          </div>
          <div>
            <h1 className="text-xl font-bold font-serif text-[#1a1715]">Direct Access Enabled</h1>
            <p className="text-xs font-mono font-bold text-amber-800">No signup required &bull; Guest workspace ready</p>
          </div>
        </div>

        <div className="rounded-xl border-2 border-[#231f1d] bg-[#fef3c7] p-4 text-xs text-[#1a1715] space-y-2 mb-6 shadow-[2px_2px_0px_#231f1d]">
          <div className="flex items-center gap-2 text-amber-900 font-bold">
            <ShieldCheck className="size-4" />
            <span>Automatic Instant Access</span>
          </div>
          <p className="font-sans leading-relaxed">
            You can use all features of RESOLVE — including multi-agent analysis, 3D knowledge graph, document vault, and real appeal generation — without creating an account.
          </p>
        </div>

        <div className="space-y-3">
          <Link
            href="/dashboard"
            className="flex items-center justify-center gap-2 w-full rounded-xl bg-amber-400 border-2 border-[#231f1d] px-4 py-3.5 text-center text-sm font-bold text-[#1a1715] shadow-[3px_3px_0px_#231f1d] transition hover:-translate-y-0.5 hover:bg-amber-300"
          >
            <span>Enter Dashboard Directly</span>
            <ArrowRight className="size-4" />
          </Link>
          <div className="flex items-center justify-center gap-2 pt-2 text-xs font-mono text-stone-500">
            <Loader2 className="size-3.5 animate-spin" />
            <span>Redirecting to your workspace...</span>
          </div>
        </div>
      </section>
    </main>
  );
}
