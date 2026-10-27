"use client";

import { useEffect, useState } from "react";

export type Lang = "en" | "ta";
const KEY = "resolve:pref-language";
const EVENT = "resolve:lang-change";

const TA: Record<string, string> = {
  "Dashboard": "முகப்பு", "Action Fabric": "செயல் கட்டமைப்பு", "Text Splitter": "உரை பிரிப்பான்", "Decision Engine": "முடிவு இயந்திரம்",
  "New Claim": "புதிய புகார்", "My Analyses": "என் பகுப்பாய்வுகள்", "AI Assistant": "AI உதவியாளர்", "Knowledge Graph": "அறிவு வரைபடம்",
  "Cross-Domain Search": "பல துறை தேடல்", "Institution Radar": "நிறுவன ரேடார்", "Documents": "ஆவணங்கள்", "Appeals": "மேல்முறையீடுகள்",
  "Reports": "அறிக்கைகள்", "Notifications": "அறிவிப்புகள்", "Settings": "அமைப்புகள்",
  "Whisper & solve dispute": "கூறுங்கள், தீர்வு காணுங்கள்",
};

export function getLang(): Lang {
  try { return window.localStorage.getItem(KEY) === "ta" ? "ta" : "en"; } catch { return "en"; }
}

export function setLang(lang: Lang) {
  try { window.localStorage.setItem(KEY, lang); } catch { /* preference just won't persist */ }
  window.dispatchEvent(new Event(EVENT));
}

export function useLang(): { lang: Lang; t: (text: string) => string } {
  const [lang, setL] = useState<Lang>("en");
  useEffect(() => {
    const sync = () => setL(getLang());
    sync();
    window.addEventListener(EVENT, sync);
    return () => window.removeEventListener(EVENT, sync);
  }, []);
  return { lang, t: (text) => (lang === "ta" ? TA[text] ?? text : text) };
}
