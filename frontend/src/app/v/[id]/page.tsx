"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { useChapterShortcuts } from "./shortcuts";

type TranscriptSegment = { start: number; end: number; text: string };
type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

// ReactMarkdown will render assistant responses as Markdown

export default function VideoPage() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const t = search.get("t");
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [summary, setSummary] = useState<string>("");
  const [chapters, setChapters] = useState<{ title: string; start: number }[]>(
    []
  );
  const [takeaways, setTakeaways] = useState<string[]>([]);
  const [entities, setEntities] = useState<string[]>([]);
  const [entitiesByType, setEntitiesByType] = useState<{
    people: string[];
    organizations: string[];
    products: string[];
  } | null>(null);
  const [apiKey, setApiKey] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState<string>("");
  const [sending, setSending] = useState<boolean>(false);
  const [loadingTranscript, setLoadingTranscript] = useState(true);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingChapters, setLoadingChapters] = useState(true);
  const [loadingTakeaways, setLoadingTakeaways] = useState(true);
  const [loadingEntities, setLoadingEntities] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const playerRef = useRef<HTMLIFrameElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Load saved API key if present
    try {
      const saved = localStorage.getItem("ytai_openai_key") || "";
      if (saved) setApiKey(saved);
    } catch {}
  }, []);

  const withKey = useCallback(
    (init?: RequestInit): RequestInit => {
      const headers = new Headers(init?.headers || {});
      if (apiKey) headers.set("X-OpenAI-Key", apiKey);
      return { ...init, headers };
    },
    [apiKey]
  );

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
          .catch((e) =>
            setError(
              e instanceof Error ? e.message : "Failed to load transcript"
            )
          )
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
            setEntitiesByType({
              people: data.people || [],
              organizations: data.organizations || [],
              products: data.products || [],
            });
          })
          .catch(async () => {
            const en = await fetch(`${base}/api/entities/${id}`, withKey())
              .then((r) => r.json())
              .catch(() => null);
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
    try {
      chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    } catch {}
  }, [messages, sending]);

  const baseApi = useMemo(
    () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    []
  );
  const chatStorageKey = useMemo(() => `ytai_chat_${id}`, [id]);

  // Load saved chat for this video
  useEffect(() => {
    try {
      const raw = localStorage.getItem(chatStorageKey);
      if (raw) {
        const parsed = JSON.parse(raw) as ChatMessage[];
        if (Array.isArray(parsed)) setMessages(parsed);
      }
    } catch {}
  }, [chatStorageKey]);

  // Persist chat on changes (keep last 10 messages)
  useEffect(() => {
    try {
      const toSave = messages.slice(-10);
      localStorage.setItem(chatStorageKey, JSON.stringify(toSave));
    } catch {}
  }, [messages, chatStorageKey]);

  const ask = useCallback(
    async (q: string) => {
      if (!q || sending) return;
      const userMsg: ChatMessage = { role: "user", content: q };
      setMessages((m) => [...m, userMsg]);
      setPrompt("");
      setSending(true);
      try {
        const init = withKey({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            video_id: id,
            messages: [...messages, userMsg],
          }),
        });
        const res = await fetch(`${baseApi}/api/chat`, init);
        if (!res.ok) throw new Error(`Chat failed (${res.status})`);
        const data = await res.json();
        const assistant: ChatMessage = data?.message || {
          role: "assistant",
          content: "",
        };
        setMessages((m) => [...m, assistant]);
      } catch (e) {
        const err = e instanceof Error ? e.message : "Something went wrong";
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `Error: ${err}` },
        ]);
      } finally {
        setSending(false);
      }
    },
    [id, messages, sending, withKey, baseApi]
  );

  const onSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const q = prompt.trim();
      if (!q) return;
      ask(q);
    },
    [prompt, ask]
  );

  // Client-side export helpers
  const triggerDownload = useCallback(
    (filename: string, content: string, mime: string = "text/plain") => {
      try {
        const blob = new Blob([content], { type: mime });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch {}
    },
    []
  );

  const buildChatTxt = useCallback(() => {
    const lines: string[] = [
      `Video ${id} — Chat Log`,
      "",
      ...messages.map((m) => `${m.role.toUpperCase()}: ${m.content}`),
    ];
    return lines.join("\n");
  }, [id, messages]);

  const buildChatMd = useCallback(() => {
    const lines: string[] = ["# Chat Log", ""];
    messages.forEach((m) => {
      const title =
        m.role === "user"
          ? "User"
          : m.role === "assistant"
          ? "Assistant"
          : "System";
      lines.push(`### ${title}`);
      lines.push("");
      lines.push(m.content);
      lines.push("");
    });
    return lines.join("\n");
  }, [messages]);

  const buildFullTxt = useCallback(() => {
    const lines: string[] = [];
    lines.push(`Video ${id}`);
    lines.push("");
    lines.push("TL;DR");
    lines.push(summary || "");
    lines.push("");
    lines.push("Chapters");
    chapters.forEach((c) => lines.push(`${toTime(c.start)}  ${c.title}`));
    lines.push("");
    lines.push("Key Takeaways");
    takeaways.forEach((t) => lines.push(`- ${t}`));
    lines.push("");
    lines.push("Entities");
    if (entitiesByType) {
      if (entitiesByType.people?.length)
        lines.push(`People: ${entitiesByType.people.join(", ")}`);
      if (entitiesByType.organizations?.length)
        lines.push(`Organizations: ${entitiesByType.organizations.join(", ")}`);
      if (entitiesByType.products?.length)
        lines.push(`Products: ${entitiesByType.products.join(", ")}`);
    } else if (entities?.length) {
      lines.push(entities.join(", "));
    }
    lines.push("");
    lines.push("Chat Log");
    messages.forEach((m) =>
      lines.push(`${m.role.toUpperCase()}: ${m.content}`)
    );
    lines.push("");
    lines.push("Transcript");
    const fullText = segments.map((s) => s.text).join(" ");
    lines.push(fullText);
    return lines.join("\n");
  }, [
    id,
    summary,
    chapters,
    takeaways,
    entitiesByType,
    entities,
    messages,
    segments,
  ]);

  useEffect(() => {
    if (t && playerRef.current) {
      try {
        const sec = parseFloat(t);
        if (!Number.isNaN(sec)) {
          playerRef.current.src = `https://www.youtube.com/embed/${id}?start=${Math.floor(
            sec
          )}&autoplay=0`;
        }
      } catch {}
    }
  }, [t, id]);

  const miniToc = useMemo(() => {
    return chapters; // show all chapters; container is scrollable
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
            <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60 resize-y overflow-auto min-h-[180px]">
              <h2 className="text-lg font-semibold mb-2">TL;DR</h2>
              {loadingSummary ? (
                <div className="text-sm text-white/60 flex items-center">
                  <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                  Generating TL;DR…
                </div>
              ) : (
                <div className="prose prose-invert max-w-none whitespace-pre-wrap text-sm">
                  {summary}
                </div>
              )}
            </section>

            <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60">
              <h2 className="text-lg font-semibold mb-2">
                Chat about this video
              </h2>
              <div className="text-xs text-white/60 mb-3">
                Grounded to this video&apos;s transcript.{" "}
                {apiKey
                  ? "Using your API key."
                  : "Using shared limits; add your API key for better reliability."}
              </div>
              <div className="overflow-y-auto rounded border border-white/10 bg-black/20 p-3 space-y-2 resize-y h-[200px] min-h-[200px]">
                {messages.length === 0 ? (
                  <div className="text-sm text-white/50">
                    Ask anything about the content. Example: &quot;Summarize
                    this video into 100 words&quot;.
                  </div>
                ) : (
                  messages.map((m, i) => (
                    <div
                      key={i}
                      className={
                        m.role === "user" ? "text-sm" : "text-sm text-white/90"
                      }
                    >
                      <div
                        className={
                          m.role === "user"
                            ? "bg-blue-500/10 border border-blue-500/20 inline-block px-3 py-2 rounded"
                            : "bg-white/5 border border-white/10 inline-block px-3 py-2 rounded prose prose-invert max-w-none text-sm"
                        }
                      >
                        {m.role === "assistant" ? (
                          <ReactMarkdown>{m.content}</ReactMarkdown>
                        ) : (
                          <div>{m.content}</div>
                        )}
                      </div>
                    </div>
                  ))
                )}
                {sending && (
                  <div className="text-sm text-white/70 flex items-center">
                    <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                    Thinking…
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
              <form onSubmit={onSubmit} className="mt-3 flex gap-2">
                <input
                  className="flex-1 rounded bg-black/30 border border-white/10 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-white/20"
                  placeholder="Ask a question…"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  disabled={sending}
                />
                <button
                  type="submit"
                  disabled={sending || !prompt.trim()}
                  className="rounded-md bg-white text-black px-3 py-2 text-sm font-medium disabled:opacity-60"
                  aria-label="Send"
                >
                  Send
                </button>
              </form>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                {[
                  "Summarize this video into 100 words",
                  "Give 5 bullet-point insights",
                  "List major entities and their roles",
                  "Outline chapters and timestamps",
                  "What are the key takeaways?",
                ].map((q, i) => (
                  <button
                    key={i}
                    type="button"
                    disabled={sending}
                    onClick={() => ask(q)}
                    className="rounded-full border border-white/10 px-2 py-1 hover:bg-white/5 disabled:opacity-60"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60 resize-y overflow-auto min-h-[220px]">
              <h2 className="text-lg font-semibold mb-2">Transcript</h2>
              {loadingTranscript ? (
                <div className="text-sm text-white/60 flex items-center">
                  <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                  Cleaning up and punctuating…
                </div>
              ) : (
                <div className="text-sm leading-6 space-y-1 max-h-[60vh] overflow-auto">
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
        <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60 resize-y overflow-auto min-h-[140px]">
          <h3 className="text-base font-semibold mb-2">API Key (optional)</h3>
          <p className="text-xs text-white/60 mb-2">
            Provide your own OpenAI API key to improve AI quality and avoid
            shared limits. Stored locally in your browser.
          </p>
          <input
            className="w-full rounded bg-black/30 border border-white/10 px-2 py-1 text-sm"
            type="password"
            placeholder="sk-..."
            value={apiKey}
            onChange={(e) => {
              const v = e.target.value.trim();
              setApiKey(v);
              try {
                localStorage.setItem("ytai_openai_key", v);
              } catch {}
            }}
          />
        </section>
        <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto space-y-6 pr-2">
          <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60 resize-y overflow-auto min-h-[220px]">
            <h3 className="text-base font-semibold mb-2">Chapters</h3>
            {loadingChapters ? (
              <div className="text-sm text-white/60 flex items-center">
                <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                Analyzing video for chapters…
              </div>
            ) : (
              <ul className="text-sm space-y-1 max-h-[50vh] overflow-auto">
                {miniToc.map((c, i) => (
                  <li key={i}>
                    <button
                      onClick={() => jumpTo(c.start)}
                      className="text-blue-400 hover:underline w-full text-left grid grid-cols-[auto_1fr] items-start gap-2"
                      title={`Jump to ${toTime(c.start)}`}
                    >
                      <span className="font-mono tabular-nums">
                        {toTime(c.start)}
                      </span>
                      <span>{c.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60 resize-y overflow-auto min-h-[220px]">
            <h3 className="text-base font-semibold mb-2">Key takeaways</h3>
            {loadingTakeaways ? (
              <div className="text-sm text-white/60 flex items-center">
                <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                Extracting key takeaways…
              </div>
            ) : (
              <ul className="text-sm list-disc pl-5 space-y-1 max-h-[50vh] overflow-auto">
                {takeaways.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60 resize-y overflow-auto min-h-[220px]">
            <h3 className="text-base font-semibold mb-2">Entities</h3>
            {loadingEntities ? (
              <div className="text-sm text-white/60 flex items-center">
                <span className="inline-block h-3 w-3 border-2 border-white/60 border-t-transparent rounded-full animate-spin mr-2" />
                Extracting entities…
              </div>
            ) : entitiesByType ? (
              <div className="space-y-3 text-sm max-h-[50vh] overflow-auto">
                {entitiesByType.people && entitiesByType.people.length > 0 && (
                  <div>
                    <div className="font-medium mb-1">People</div>
                    <ul className="list-disc pl-5 space-y-1">
                      {entitiesByType.people.map((e, i) => (
                        <li key={i}>
                          <a
                            className="hover:underline text-blue-400"
                            href={`https://www.google.com/search?q=${encodeURIComponent(
                              e
                            )}`}
                            target="_blank"
                          >
                            {e}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {entitiesByType.organizations &&
                  entitiesByType.organizations.length > 0 && (
                    <div>
                      <div className="font-medium mb-1">Organizations</div>
                      <ul className="list-disc pl-5 space-y-1">
                        {entitiesByType.organizations.map((e, i) => (
                          <li key={i}>
                            <a
                              className="hover:underline text-blue-400"
                              href={`https://www.google.com/search?q=${encodeURIComponent(
                                e
                              )}`}
                              target="_blank"
                            >
                              {e}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                {entitiesByType.products &&
                  entitiesByType.products.length > 0 && (
                    <div>
                      <div className="font-medium mb-1">Products</div>
                      <ul className="list-disc pl-5 space-y-1">
                        {entitiesByType.products.map((e, i) => (
                          <li key={i}>
                            <a
                              className="hover:underline text-blue-400"
                              href={`https://www.google.com/search?q=${encodeURIComponent(
                                e
                              )}`}
                              target="_blank"
                            >
                              {e}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
            ) : (
              <div className="flex flex-wrap gap-2 max-h-[50vh] overflow-auto">
                {entities.map((e, i) => (
                  <a
                    key={i}
                    className="text-xs rounded-full border border-white/10 px-2 py-1 hover:bg-white/5"
                    href={`https://www.google.com/search?q=${encodeURIComponent(
                      e
                    )}`}
                    target="_blank"
                  >
                    {e}
                  </a>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-lg border border-white/10 p-4 bg-neutral-900/60 resize-y overflow-auto min-h-[160px]">
            <h3 className="text-base font-semibold mb-2">Export</h3>
            <div className="space-y-3 text-sm">
              <div>
                <div className="font-medium mb-1">Full Page</div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="underline"
                    onClick={() =>
                      triggerDownload(
                        `${id}-full.txt`,
                        buildFullTxt(),
                        "text/plain"
                      )
                    }
                  >
                    txt
                  </button>
                  <a
                    className="underline"
                    href={`${baseApi}/api/export/full/md/${id}`}
                    download={`${id}-full.md`}
                  >
                    markdown
                  </a>
                </div>
              </div>
              <div>
                <div className="font-medium mb-1">Transcript</div>
                <div className="flex flex-wrap gap-2">
                  <a
                    className="underline"
                    href={`${baseApi}/api/export/txt/${id}`}
                    download={`${id}.txt`}
                  >
                    txt
                  </a>
                  <a
                    className="underline"
                    href={`${baseApi}/api/export/srt/${id}`}
                    download={`${id}.srt`}
                  >
                    srt
                  </a>
                  <a
                    className="underline"
                    href={`${baseApi}/api/export/vtt/${id}`}
                    download={`${id}.vtt`}
                  >
                    vtt
                  </a>
                  <a
                    className="underline"
                    href={`${baseApi}/api/export/transcript/json/${id}`}
                    download={`${id}-transcript.json`}
                  >
                    json
                  </a>
                </div>
              </div>
              <div>
                <div className="font-medium mb-1">AI Chat</div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="underline"
                    onClick={() =>
                      triggerDownload(
                        `${id}-chat.txt`,
                        buildChatTxt(),
                        "text/plain"
                      )
                    }
                  >
                    txt
                  </button>
                  <button
                    className="underline"
                    onClick={() =>
                      triggerDownload(
                        `${id}-chat.md`,
                        buildChatMd(),
                        "text/markdown"
                      )
                    }
                  >
                    markdown
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}
