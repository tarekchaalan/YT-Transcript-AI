"use client";

import { Suspense, useEffect, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

function parseYouTubeTimeToSeconds(val: string | null): number | null {
  if (!val) return null;
  try {
    const v = String(val).trim().toLowerCase();
    if (/^\d+$/.test(v)) return Math.max(0, parseInt(v, 10));
    const secOnly = v.match(/^(\d+)s$/);
    if (secOnly) return Math.max(0, parseInt(secOnly[1], 10));
    const h = v.match(/(\d+)h/);
    const m = v.match(/(\d+)m/);
    const s = v.match(/(\d+)s/);
    const hours = h ? parseInt(h[1], 10) : 0;
    const mins = m ? parseInt(m[1], 10) : 0;
    const secs = s ? parseInt(s[1], 10) : 0;
    const total = hours * 3600 + mins * 60 + secs;
    return Number.isFinite(total) && total >= 0 ? total : null;
  } catch {
    return null;
  }
}

function WatchRedirectInner() {
  const router = useRouter();
  const params = useSearchParams();

  const { id, t } = useMemo(() => {
    const v = params.get("v") || "";
    const id = /^[a-zA-Z0-9_-]{11}$/.test(v) ? v : null;
    const tRaw = params.get("t") || params.get("time_continue");
    const t = parseYouTubeTimeToSeconds(tRaw);
    return { id, t };
  }, [params]);

  useEffect(() => {
    if (!id) return;
    const dest = t != null ? `/v/${id}?t=${t}` : `/v/${id}`;
    router.replace(dest);
  }, [id, t, router]);

  const manualHref = id ? (t != null ? `/v/${id}?t=${t}` : `/v/${id}`) : "/";

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 text-sm text-white/80">
      <div className="rounded-lg border border-white/10 p-4 bg-neutral-900/60">
        {id ? (
          <div>
            Redirecting to <Link className="underline" href={manualHref}>/v/{id}</Link>…
          </div>
        ) : (
          <div>
            Missing or invalid <code>v</code> parameter. Go back to <Link className="underline" href="/">home</Link>.
          </div>
        )}
      </div>
    </div>
  );
}

export default function WatchRedirectPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-2xl px-4 py-10 text-sm text-white/80">Loading…</div>}>
      <WatchRedirectInner />
    </Suspense>
  );
}


