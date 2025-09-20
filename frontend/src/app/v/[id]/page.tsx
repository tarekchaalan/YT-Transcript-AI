"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { useChapterShortcuts } from "./shortcuts";

type TranscriptSegment = { start: number; end: number; text: string };

export default function VideoPage() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const t = search.get("t");
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [summary, setSummary] = useState<string>("");
  const [chapters, setChapters] = useState<{ title: string; start: number }[]>([]);
  const [takeaways, setTakeaways] = useState<string[]>([]);
  const [entities, setEntities] = useState<string[]>([]);
  const [entitiesByType, setEntitiesByType] = useState<{ people: string[]; organizations: string[]; products: string[] } | null>(null);
  const [apiKey, setApiKey] = useState<string>("");
  const [loadingTranscript, setLoadingTranscript] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingChapters, setLoadingChapters] = useState(true);
  const [loadingTakeaways, setLoadingTakeaways] = useState(true);
  const [loadingEntities, setLoadingEntities] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const playerRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    // Load saved API key if present
    try {
      const saved = localStorage.getItem("ytai_openai_key") || "";
      if (saved) setApiKey(saved);
    } catch {}
  }, []);

  const withKey = useCallback((init?: RequestInit): RequestInit => {
    const headers = new Headers(init?.headers || {});
    if (apiKey) headers.set("X-OpenAI-Key", apiKey);
    return { ...init, headers };
  }, [apiKey]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        // Kick off all requests in parallel and update each section as it returns
        setLoadingTranscript(true);
        setLoadingSummary(true);
        setLoadingChapters(true);
        setLoadingTakeaways(true);
        setLoadingEntities(true);

        // Transcript first to allow reading and jumping quickly
        fetch(`${base}/api/transcript/${id}`)
          .then((r) => r.json())
          .then((tr) => {
            if (cancelled) return;
            setSegments(tr.segments || []);
            setError(null);
          })
          .catch((e) => setError(e instanceof Error ? e.message : "Failed to load transcript"))
          .finally(() => setLoadingTranscript(false));

        fetch(`${base}/api/summary/${id}`, withKey())
          .then((r) => r.json())
          .then((sm) => {
            if (cancelled) return;
            setSummary(sm.summary || "");
          })
          .finally(() => setLoadingSummary(false));

        fetch(`${base}/api/chapters/${id}`, withKey())
          .then((r) => r.json())
          .then((ch) => {
            if (cancelled) return;
            setChapters(ch.chapters || []);
          })
          .finally(() => setLoadingChapters(false));

        fetch(`${base}/api/takeaways/${id}`, withKey())
          .then((r) => r.json())
          .then((tk) => {
            if (cancelled) return;
            setTakeaways(tk.takeaways || []);
          })
          .finally(() => setLoadingTakeaways(false));

        // Prefer categorized endpoint; fallback to flat
        fetch(`${base}/api/entities/by-type/${id}`, withKey())
          .then(async (r) => {
            if (!r.ok) throw new Error("entities by type not available");
            return r.json();
          })
          .then((data) => {
            if (cancelled) return;
            setEntitiesByType({ people: data.people || [], organizations: data.organizations || [], products: data.products || [] });
          })
          .catch(async () => {
            const en = await fetch(`${base}/api/entities/${id}`, withKey()).then((r) => r.json()).catch(() => null);
            if (!en) return;
            if (cancelled) return;
            setEntities(en.entities || []);
          })
          .finally(() => setLoadingEntities(false));
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to load data";
        setError(msg);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [id, apiKey, withKey]);

  useEffect(() => {
    if (t && playerRef.current) {
      try {
        const sec = parseFloat(t);
        if (!Number.isNaN(sec)) {
          playerRef.current.src = `https://www.youtube.com/embed/${id}?start=${Math.floor(sec)}&autoplay=0`;
        }
      } catch {}
    }
  }, [t, id]);

  const miniToc = useMemo(() => {
    return chapters.slice(0, 12);
  }, [chapters]);

  function jumpTo(second: number) {
    const url = new URL(window.location.href);
    url.searchParams.set("t", String(Math.floor(second)));
    router.push(url.pathname + url.search);
  }

  function toTime(s: number) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    return `${h.toString().padStart(2, "0")}:${m
      .toString()
      .padStart(2, "0")}:${sec.toString().padStart(2, "0")}`;
  }

  useChapterShortcuts(chapters, jumpTo);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 grid md:grid-cols-[3fr_2fr] gap-6">
      <div className="space-y-6">
        <div className="aspect-video w-full overflow-hidden rounded-lg border border-white/10 bg-black">
          <iframe
            ref={playerRef}
            className="h-full w-full"
            src={`https://www.youtube.com/embed/${id}`}
            title="YouTube video player"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
          />
        </div>

        {error ? (
          <div className="text-sm text-red-400">{error}</div>
        ) : (
          <>
            <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60">
              <h2 className="text-lg font-semibold mb-2">TL;DR</h2>
              {loadingSummary ? (
                <div className="text-sm text-white/60 flex items-center">
                  <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                  Generating TL;DR…
                </div>
              ) : (
                <div className="prose prose-invert max-w-none whitespace-pre-wrap text-sm">{summary}</div>
              )}
            </section>

            <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60">
              <h2 className="text-lg font-semibold mb-2">Transcript</h2>
              {loadingTranscript ? (
                <div className="text-sm text-white/60 flex items-center">
                  <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                  Cleaning up and punctuating…
                </div>
              ) : (
                <div className="text-sm leading-6 space-y-1">
                  {segments.map((s, i) => (
                    <div key={i} className="hover:bg-white/5 rounded px-1">
                      <button
                        onClick={() => jumpTo(s.start)}
                        className="text-xs text-blue-400 hover:underline mr-2"
                      >
                        {toTime(s.start)}
                      </button>
                      <span>{s.text}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>

      <aside className="space-y-6">
        <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60">
          <h3 className="text-base font-semibold mb-2">API Key (optional)</h3>
          <p className="text-xs text-white/60 mb-2">Provide your own OpenAI API key to improve AI quality and avoid shared limits. Stored locally in your browser.</p>
          <input
            className="w-full rounded bg-black/30 border border-white/10 px-2 py-1 text-sm"
            type="password"
            placeholder="sk-..."
            value={apiKey}
            onChange={(e) => {
              const v = e.target.value.trim();
              setApiKey(v);
              try { localStorage.setItem("ytai_openai_key", v); } catch {}
            }}
          />
        </section>
        <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto space-y-6 pr-2">
          <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60">
            <h3 className="text-base font-semibold mb-2">Chapters</h3>
            {loadingChapters ? (
              <div className="text-sm text-white/60 flex items-center">
                <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                Analyzing video for chapters…
              </div>
            ) : (
              <ul className="text-sm space-y-1">
                {miniToc.map((c, i) => (
                  <li key={i}>
                    <button
                      onClick={() => jumpTo(c.start)}
                      className="text-blue-400 hover:underline w-full text-left grid grid-cols-[auto_1fr] items-start gap-2"
                      title={`Jump to ${toTime(c.start)}`}
                    >
                      <span className="font-mono tabular-nums">{toTime(c.start)}</span>
                      <span>{c.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60">
            <h3 className="text-base font-semibold mb-2">Key takeaways</h3>
            {loadingTakeaways ? (
              <div className="text-sm text-white/60 flex items-center">
                <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                Extracting key takeaways…
              </div>
            ) : (
              <ul className="text-sm list-disc pl-5 space-y-1">
                {takeaways.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60">
            <h3 className="text-base font-semibold mb-2">Entities</h3>
            {loadingEntities ? (
              <div className="text-sm text-white/60 flex items-center">
                <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                Extracting entities…
              </div>
            ) : entitiesByType ? (
              <div className="space-y-3 text-sm">
                {entitiesByType.people && entitiesByType.people.length > 0 && (
                  <div>
                    <div className="font-medium mb-1">People</div>
                    <ul className="list-disc pl-5 space-y-1">
                      {entitiesByType.people.map((e, i) => (
                        <li key={i}><a className="hover:underline text-blue-400" href={`https://www.google.com/search?q=${encodeURIComponent(e)}`} target="_blank">{e}</a></li>
                      ))}
                    </ul>
                  </div>
                )}
                {entitiesByType.organizations && entitiesByType.organizations.length > 0 && (
                  <div>
                    <div className="font-medium mb-1">Organizations</div>
                    <ul className="list-disc pl-5 space-y-1">
                      {entitiesByType.organizations.map((e, i) => (
                        <li key={i}><a className="hover:underline text-blue-400" href={`https://www.google.com/search?q=${encodeURIComponent(e)}`} target="_blank">{e}</a></li>
                      ))}
                    </ul>
                  </div>
                )}
                {entitiesByType.products && entitiesByType.products.length > 0 && (
                  <div>
                    <div className="font-medium mb-1">Products</div>
                    <ul className="list-disc pl-5 space-y-1">
                      {entitiesByType.products.map((e, i) => (
                        <li key={i}><a className="hover:underline text-blue-400" href={`https://www.google.com/search?q=${encodeURIComponent(e)}`} target="_blank">{e}</a></li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {entities.map((e, i) => (
                  <a
                    key={i}
                    className="text-xs rounded-full border border-white/10 px-2 py-1 hover:bg-white/5"
                    href={`https://www.google.com/search?q=${encodeURIComponent(e)}`}
                    target="_blank"
                  >
                    {e}
                  </a>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60">
            <h3 className="text-base font-semibold mb-2">Export</h3>
            <div className="flex flex-wrap gap-2 text-sm">
              <a className="underline" href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/export/txt/${id}`} download={`${id}.txt`}>.txt</a>
              <a className="underline" href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/export/srt/${id}`} download={`${id}.srt`}>.srt</a>
              <a className="underline" href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/export/vtt/${id}`} download={`${id}.vtt`}>.vtt</a>
              <a className="underline" href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/export/chapters/${id}`} download={`${id}-chapters.json`}>chapters.json</a>
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}


