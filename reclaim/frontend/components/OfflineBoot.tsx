"use client";

import { installOfflineFetch } from "@/lib/offline-api";

// Patches window.fetch once, at module load in the browser, so every page's
// first request is already covered by the demo backend fallback.
if (typeof window !== "undefined") installOfflineFetch();

export function OfflineBoot() {
  return null;
}
