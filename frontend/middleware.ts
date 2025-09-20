import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

function extractIdFromUrlPath(pathname: string, search: string): string | null {
  const full = `https://youtube.com${pathname}${search}`;
  const patterns = [
    /[?&]v=([a-zA-Z0-9_-]{11})/, // watch?v=
    /youtu\.be\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/,
    /youtube\.com\/live\/([a-zA-Z0-9_-]{11})/,
    /\b([a-zA-Z0-9_-]{11})\b/,
  ];
  for (const re of patterns) {
    const m = full.match(re);
    if (m) return m[1];
  }
  return null;
}

function parseYouTubeTimeToSeconds(search: string): number | null {
  try {
    const params = new URLSearchParams(search || "");
    const raw = params.get("t") || params.get("time_continue");
    if (!raw) return null;
    const val = String(raw).trim().toLowerCase();
    // Examples: 90, 90s, 1m30s, 1h2m3s
    if (/^\d+$/.test(val)) return Math.max(0, parseInt(val, 10));
    const secOnly = val.match(/^(\d+)s$/);
    if (secOnly) return Math.max(0, parseInt(secOnly[1], 10));
    const h = val.match(/(\d+)h/);
    const m = val.match(/(\d+)m/);
    const s = val.match(/(\d+)s/);
    const hours = h ? parseInt(h[1], 10) : 0;
    const mins = m ? parseInt(m[1], 10) : 0;
    const secs = s ? parseInt(s[1], 10) : 0;
    const total = hours * 3600 + mins * 60 + secs;
    return Number.isFinite(total) && total >= 0 ? total : null;
  } catch {
    return null;
  }
}

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  // Skip next internal, static files, api, and our canonical route
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/v/") ||
    pathname === "/"
  ) {
    return NextResponse.next();
  }

  // Special-case standard YouTube watch path for reliability
  let id: string | null = null;
  if (pathname === "/watch") {
    const v = req.nextUrl.searchParams.get("v") || "";
    if (/^[a-zA-Z0-9_-]{11}$/.test(v)) {
      id = v;
    }
  }
  if (!id) {
    id = extractIdFromUrlPath(pathname, search);
  }
  if (id) {
    const t = parseYouTubeTimeToSeconds(search);
    const dest = new URL(`/v/${id}`, req.url);
    if (t != null) dest.searchParams.set("t", String(t));
    // Rewrite to internal route
    return NextResponse.rewrite(dest);
  }
  return NextResponse.next();
}

export const config = {
  // Run on all pages except API, Next internals, and files with extensions
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};


