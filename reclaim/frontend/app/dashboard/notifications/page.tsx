import { NotificationsCenter } from "@/components/notifications/NotificationsCenter";

export default function Page() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-6">
        <span className="font-mono text-[10px] font-black uppercase tracking-wider text-amber-700">
          [ ◈ REAL-TIME REGULATORY DISPUTE AUDIT ]
        </span>
        <h1 className="mt-1 font-mono text-3xl sm:text-4xl font-black tracking-tight text-[#1c1917]">
          Activity Notifications &amp; Alerts
        </h1>
        <p className="mt-2 max-w-3xl text-xs font-medium leading-5 text-stone-600">
          Real-time event feed covering case status transitions, document parsing, evidence indexing, and multi-agent appeal generations across all 8 consumer domains.
        </p>
      </header>
      <NotificationsCenter />
    </div>
  );
}
