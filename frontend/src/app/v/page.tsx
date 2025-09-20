"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

function VRedirectInner() {
  const search = useSearchParams();
  const router = useRouter();
  useEffect(() => {
    const url = search.get("url");
    if (!url) return;
    const id = extractYouTubeId(url);
    if (id) {
      router.replace(`/v/${id}`);
    }
  }, [search, router]);
  return null;
}

export default function VRedirect() {
  return (
    <Suspense fallback={null}>
      <VRedirectInner />
    </Suspense>
  );
}

function extractYouTubeId(url: string): string | null {
  try {
    const patterns = [
      /[?&]v=([a-zA-Z0-9_-]{11})/,
      /youtu\.be\/([a-zA-Z0-9_-]{11})/,
      /youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})/,
      /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/,
      /\b([a-zA-Z0-9_-]{11})\b/,
    ];
    for (const re of patterns) {
      const m = url.match(re);
      if (m) return m[1];
    }
    return null;
  } catch {
    return null;
  }
}


