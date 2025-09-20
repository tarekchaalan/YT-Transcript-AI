"use client";

import { useEffect } from "react";

export function useChapterShortcuts(chapters: { start: number }[], onJump: (s: number) => void) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target && (e.target as HTMLElement).tagName === "INPUT") return;
      if (!chapters || chapters.length === 0) return;
      const t = getCurrentSecondFromUrl();
      if (e.key === "j") {
        const next = chapters.find((c) => c.start > t);
        if (next) onJump(next.start);
      } else if (e.key === "k") {
        const prev = [...chapters].reverse().find((c) => c.start < t);
        if (prev) onJump(prev.start);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chapters, onJump]);
}

function getCurrentSecondFromUrl(): number {
  try {
    const url = new URL(window.location.href);
    const t = parseFloat(url.searchParams.get("t") || "0");
    if (!Number.isFinite(t)) return 0;
    return Math.max(0, Math.floor(t));
  } catch {
    return 0;
  }
}


