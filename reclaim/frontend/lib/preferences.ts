export const PREF_KEYS = {
  notificationsLive: "resolve:pref-notifications-live",
  notificationsPollMs: "resolve:pref-notifications-poll-ms",
  kgDefaultTab: "resolve:pref-kg-default-tab",
  newAnalysisDefaultDomain: "resolve:pref-new-analysis-domain",
} as const;

export function getPref(key: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return window.localStorage.getItem(key) ?? fallback;
}

export function setPref(key: string, value: string) {
  window.localStorage.setItem(key, value);
}
