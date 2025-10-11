from __future__ import annotations

import os
import contextvars
import re
from typing import List, Optional
import json
import hashlib
from typing import Callable, Any
import time
import math
import collections

import yake

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
_override_openai_key: contextvars.ContextVar[str | None] = contextvars.ContextVar("override_openai_key", default=None)

_openai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI  # type: ignore

        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        _openai_client = None


def _effective_openai_key() -> Optional[str]:
    override = _override_openai_key.get()
    return override or OPENAI_API_KEY


def _log_ai_event(event: str, details: dict[str, Any]) -> None:
    """Lightweight logging controlled by env LOG_AI=1."""
    try:
        if os.environ.get("LOG_AI") != "1":
            return
        safe_details = {k: v for k, v in details.items() if k not in {"prompt"}}
        print(f"[AI] {event} | {json.dumps(safe_details, ensure_ascii=False)}")
    except Exception:
        pass


def _call_openai(
    prompt: str,
    system: str = "You are a helpful assistant.",
    *,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    presence_penalty: float = 0.0,
    frequency_penalty: float = 0.0,
    top_p: float = 0.0,
    response_format: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    key = _effective_openai_key()
    if not key:
        return None
    try:
        # Create a short-lived client with the effective key to avoid cross-request leakage
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=key)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        prompt_bytes = len(prompt.encode("utf-8", errors="ignore"))
        system_bytes = len(system.encode("utf-8", errors="ignore"))
        prompt_hash = hashlib.sha256((system + "\n" + prompt).encode("utf-8", errors="ignore")).hexdigest()
        t0 = time.time()
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
            "top_p": top_p,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        resp = client.chat.completions.create(**kwargs)
        out = resp.choices[0].message.content  # type: ignore[assignment]
        try:
            finish_reason = getattr(resp.choices[0], "finish_reason", None)
        except Exception:
            finish_reason = None
        # Check if any reasoning-like field exists without logging content
        reasoning_present = False
        try:
            ch0 = resp.choices[0]
            reasoning_present = bool(
                getattr(getattr(ch0, "message", object()), "reasoning", None)
                or getattr(ch0, "logprobs", None)
            )
        except Exception:
            reasoning_present = False
        dt = int((time.time() - t0) * 1000)
        response_bytes = len((out or "").encode("utf-8", errors="ignore"))
        _log_ai_event(
            "openai_call",
            {
                "model": model,
                "prompt_bytes": prompt_bytes + system_bytes,
                "response_bytes": response_bytes,
                "latency_ms": dt,
                "finish_reason": finish_reason,
                "prompt_hash": prompt_hash,
                "reasoning_present": reasoning_present,
            },
        )
        return out  # type: ignore[return-value]
    except Exception:
        return None


def override_openai_key_for_request(key: Optional[str]):
    """Context manager to apply per-request OpenAI key override safely."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        token = _override_openai_key.set(key)
        try:
            yield
        finally:
            _override_openai_key.reset(token)

    return _ctx()


def _token_clip(text: str, max_tokens: int, model_hint: str = "gpt-4o-mini") -> str:
    """Clip text by tokens using tiktoken if available; fallback to rough char heuristic."""
    try:
        import tiktoken  # type: ignore
        try:
            enc = tiktoken.encoding_for_model(model_hint)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        clipped = enc.decode(tokens[:max_tokens])
        return clipped
    except Exception:
        # Rough heuristic ~4 chars per token
        approx_chars = max_tokens * 4
        return text[:approx_chars]


def _sanitize_title(title: str, max_len: int = 60) -> str:
    # Remove numbering/bullets and collapse whitespace; strip trailing punctuation
    t = title.strip().lstrip("•-–—0123456789. )(").strip()
    t = t.strip("\"'”’“‘")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[\s\-–—]*[\.;:!,]+$", "", t).strip()
    if len(t) > max_len:
        t = t[:max_len].rstrip()
    return t


def _safe_json(s: str) -> Optional[dict]:
    """Try to parse JSON object. If whole string fails, attempt largest balanced JSON object.

    Returns dict if successful, else None.
    """
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    # Balanced brace scan respecting strings/escapes
    best_span: tuple[int, int] | None = None
    in_str = False
    escape = False
    depth = 0
    start_idx = -1
    for i, ch in enumerate(s):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                if depth == 0:
                    start_idx = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start_idx >= 0:
                        # Candidate complete JSON object
                        span = (start_idx, i + 1)
                        if best_span is None or (span[1] - span[0]) > (best_span[1] - best_span[0]):
                            best_span = span
    if best_span:
        chunk = s[best_span[0]:best_span[1]]
        try:
            parsed2 = json.loads(chunk)
            return parsed2 if isinstance(parsed2, dict) else None
        except Exception:
            return None
    return None


_YAKE_CACHE_CAP = 256
_yake_cache: "collections.OrderedDict[str, List[tuple[str, float]]]" = collections.OrderedDict()


def _detect_lang(text: str) -> str:
    try:
        from langdetect import detect  # type: ignore
        return detect(text)
    except Exception:
        return "en"


def extract_keyphrases(text: str, max_phrases: int = 12) -> List[str]:
    # Cache by text hash and parameters
    h = hashlib.sha256((text + f"|{max_phrases}").encode("utf-8", errors="ignore")).hexdigest()
    if h in _yake_cache:
        candidates = _yake_cache.pop(h)
        _yake_cache[h] = candidates  # move to end (recent)
    else:
        lang = os.environ.get("YAKE_LANG") or _detect_lang(text)
        window = int(os.environ.get("YAKE_WINDOW", "3"))
        kw = yake.KeywordExtractor(
            lan=lang,
            top=max_phrases * 2,
            n=3,  # Up to 3-word phrases
            stopwords=None,
            dedupLim=0.7,
            windowsSize=max(3, min(4, window)),
        )
        candidates = kw.extract_keywords(text)
        _yake_cache[h] = candidates
        if len(_yake_cache) > _YAKE_CACHE_CAP:
            _yake_cache.popitem(last=False)

    # Filter and clean phrases
    cleaned = []
    for phrase, score in candidates:
        phrase = re.sub(r"\s+", " ", phrase).strip().strip("-•·•")
        # Skip single common words and very short phrases
        if (len(phrase) > 3 and
            phrase.lower() not in ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'] and
            phrase not in cleaned and
            len(phrase.split()) >= 2):  # Prefer multi-word phrases
            cleaned.append(phrase)

        if len(cleaned) >= max_phrases:
            break

    return cleaned


def summarize(text: str) -> str:
    text_clip = _token_clip(text, max_tokens=3500)
    prompt = (
        "Summarize in 5–8 bullets, 12–22 words each. No sub-bullets, one bullet per line:\n" + text_clip
    )
    ai = _call_openai(
        prompt,
        system="Return ONLY bullets starting with '-' and a newline after EACH bullet. No other text.",
        max_tokens=500,
        presence_penalty=0.0,
        frequency_penalty=0.0,
    )
    if ai:
        # Enforce bullet-only output by regex filtering
        lines = [l for l in ai.splitlines() if l.strip().startswith("- ")]
        # enforce word count bounds 12..24
        def wc(s: str) -> int:
            return len([w for w in re.findall(r"\b\w+\b", s)])
        lines = [l for l in lines if 12 <= wc(l) <= 24]
        if 5 <= len(lines) <= 8:
            return "\n".join(lines[:8])

    # Better fallback: extract sentences and create summary
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    # Get key phrases for context
    key_phrases = extract_keyphrases(text, 6)

    # Create summary from key phrases and important sentences
    summary_parts = []

    # Add overview based on key phrases
    if key_phrases:
        summary_parts.append(f"This video discusses {', '.join(key_phrases[:3]).lower()}")

    # Find sentences that contain key phrases
    important_sentences = []
    for phrase in key_phrases[:4]:
        for sentence in sentences[:20]:  # Check first 20 sentences
            if phrase.lower() in sentence.lower() and len(sentence) < 150:
                important_sentences.append(sentence)
                break

    # Add the most important sentences
    for sentence in important_sentences[:4]:
        summary_parts.append(f"• {sentence.strip()}")

    if not summary_parts:
        # Last resort: use first few sentences
        summary_parts = [f"• {s}" for s in sentences[:5] if len(s) < 120]

    return "\n".join(summary_parts) or text[:500]


def chapters(text: str, duration: float | None = None) -> List[tuple[str, float]]:
    text_clip = _token_clip(text, max_tokens=3500)
    # Ask for JSON first
    system = 'Return ONLY JSON: {"chapters":[{"title":"...","start":0},...]}'
    user = '{"task":"chapters","rules":["strict","int_seconds"]}\nTranscript:\n' + text_clip

    ai = None
    for i in range(2):
        ai = _call_openai(
            user,
            system=system,
            max_tokens=600,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            top_p=0.0,
            response_format={"type": "json_object"},
        )
        if ai:
            break
        time.sleep(0.5 * (2 ** i))
    items: List[tuple[str, float]] = []
    parse_ok = False
    if ai:
        data = _safe_json(ai)
        if data is not None:
            try:
                for c in data.get("chapters", []) or []:
                    title = _sanitize_title(str(c.get("title", "")))
                    start = float(int(c.get("start", 0)))
                    if title:
                        items.append((title, start))
                parse_ok = len(items) > 0
            except Exception:
                parse_ok = False
    if not parse_ok:
        # Retry once with harsher system
        ai2 = None
        for i in range(2):
            ai2 = _call_openai(
                user,
                system='Return ONLY JSON: {"chapters": []}. If format would be wrong, output exactly {"chapters": []}',
                max_tokens=400,
                presence_penalty=0.0,
                frequency_penalty=0.0,
                top_p=0.0,
                response_format={"type": "json_object"},
            )
            if ai2:
                break
            time.sleep(0.5 * (2 ** i))
        if ai2:
            try:
                data2 = _safe_json(ai2)
                if data2 is not None:
                    for c in data2.get("chapters", []) or []:
                        title = _sanitize_title(str(c.get("title", "")))
                        start = float(int(c.get("start", 0)))
                        if title:
                            items.append((title, start))
                    parse_ok = len(items) > 0
            except Exception:
                parse_ok = False
    if items:
        # Filter out generic titles
        generic = {"introduction", "overview", "conclusion", "finale", "final thoughts", "summary"}
        items = [(t, s) for (t, s) in items if t.strip().lower() not in generic]
        return _postprocess_chapters(items, duration)
    # fallback: evenly spaced chapters titled by keyphrases
    num = 8
    if duration and duration > 0:
        interval = duration / num
    else:
        interval = 120.0
    phrases = extract_keyphrases(text, num)
    return [(phrases[i] if i < len(phrases) else f"Chapter {i+1}", i * interval) for i in range(num)]


def _format_ts_vtt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}.000"


def _postprocess_chapters(items: List[tuple[str, float]], duration: float | None) -> List[tuple[str, float]]:
    # Clamp, sort, dedupe, and enforce increasing with a min-gap
    # Stronger gap: avoid micro-chapters; scale with duration
    min_gap = max(20.0, (duration or 0) / 60.0)
    out: List[tuple[str, float]] = []
    # Normalize
    norm: List[tuple[str, float]] = []
    for t, s in items:
        try:
            s_float = float(s)
        except Exception:
            continue
        if s_float < 0:
            s_float = 0.0
        if duration is not None and s_float > duration:
            s_float = max(0.0, float(duration))
        norm.append((t, s_float))
    # Sort by time
    norm.sort(key=lambda x: x[1])
    last = -1e9
    for title, ts in norm:
        if out and title == out[-1][0] and abs(ts - out[-1][1]) < 5:
            # same title and near-duplicate time -> skip
            continue
        if ts <= last + min_gap:
            ts = last + min_gap
        if duration is not None and ts > duration:
            break
        out.append((title, ts))
        last = ts
    # Ensure we have at least 5 items if possible by loosening min_gap slightly
    if len(out) < 5 and len(norm) >= 5:
        out = []
        last = -1e9
        for title, ts in sorted(norm, key=lambda x: x[1]):
            if ts <= last + 10.0:
                continue
            if duration is not None and ts > duration:
                break
            out.append((title, ts))
            last = ts
            if len(out) >= 5:
                break
    return out[:10]


def chapters_from_segments(segments: List[object], duration: float | None = None) -> List[tuple[str, float]]:
    """Generate chapters using VTT built from segments so the model can align content to time.

    Falls back to text-only chapters() if the AI parse fails.
    """
    # Build compact VTT (truncate to avoid token limits)
    vtt_lines: List[str] = ["WEBVTT", ""]
    total = 0
    cue_starts: List[float] = []
    for seg in segments:
        try:
            start = float(getattr(seg, "start"))
            end = float(getattr(seg, "end"))
            text = str(getattr(seg, "text", "")).strip()
        except Exception:
            continue
        if not text:
            continue
        vtt_lines.append(f"{_format_ts_vtt(start)} --> {_format_ts_vtt(end)}")
        vtt_lines.append(text)
        vtt_lines.append("")
        cue_starts.append(start)
        total += len(text)
        if total > 16000:
            break
    vtt_blob = "\n".join(vtt_lines)

    # Prepare allowed (rounded) cue start seconds for post-validation/snap
    import bisect
    rounded_cue_starts = sorted({int(round(s)) for s in cue_starts if s >= 0})
    if not rounded_cue_starts:
        # Fallback to text-based
        text = " ".join(getattr(seg, "text", "") for seg in segments)
        fallback_duration = float(getattr(segments[-1], "end", 0.0)) if segments else duration
        return chapters(text, fallback_duration)

    # Build strict prompt/system
    system_msg = (
        "Return ONLY JSON: {\"chapters\":[{\"title\":\"...\",\"start\":0},...]}"
    )
    dur_note = (
        f"\n- Video duration (seconds): {int(duration)}. All start_seconds MUST be integers in [0, duration)."
        if duration is not None else ""
    )
    cue_seconds_full = sorted({int(round(s)) for s in cue_starts if s >= 0})
    # Downsample cue list if too large
    if len(cue_seconds_full) > 3000:
        n = max(2, len(cue_seconds_full) // 1500)
        down = cue_seconds_full[::n]
        # ensure boundaries included
        if down and cue_seconds_full[0] != down[0]:
            down = [cue_seconds_full[0]] + down
        if down and cue_seconds_full[-1] != down[-1]:
            down = down + [cue_seconds_full[-1]]
        cue_seconds_list = down
    else:
        cue_seconds_list = cue_seconds_full
    prompt = (
        '{"task":"chapters","rules":['
        '"strict","int_seconds",'
        '"count_5_to_10",'
        '"min_gap_seconds:35",'
        '"cover_full_span",'
        '"snap_to_allowed",'
        '"title_3_to_7_words",'
        '"no_generic_titles:[Introduction,Overview,Conclusion,Final Thoughts,Summary]",'
        '"title_max_len:60",'
        '"title_must_include_a_specific_noun_or_action_from_nearby_cues"],'
        '"allowed_start_seconds":' + json.dumps(cue_seconds_list) + '}' "\n"
        "WEBVTT:\n" + vtt_blob
    )

    ai = None
    for i in range(2):
        ai = _call_openai(
            prompt,
            system=system_msg,
            max_tokens=800,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            top_p=0.0,
            response_format={"type": "json_object"},
        )
        if ai:
            break
        time.sleep(0.5 * (2 ** i))

    def _snap_to_cue_seconds(x: int) -> int | None:
        # Snap to the nearest allowed cue start at or after x; if none, snap to the last allowed < duration.
        idx = bisect.bisect_left(rounded_cue_starts, x)
        if idx < len(rounded_cue_starts):
            return rounded_cue_starts[idx]
        return rounded_cue_starts[-1] if rounded_cue_starts else None

    if ai:
        items: List[tuple[str, float]] = []
        try:
            m = re.search(r"\{.*\}", ai, re.S)
            if m:
                data = json.loads(m.group(0))
                chapters_json = data.get("chapters", []) or []
                used_seconds: set[int] = set()
                last_start: int | None = None
                for c in chapters_json:
                    raw_title = str(c.get("title", ""))
                    title = _sanitize_title(raw_title)
                    try:
                        sec_int = int(c.get("start", 0))
                    except Exception:
                        continue
                    snapped = _snap_to_cue_seconds(sec_int)
                    if snapped is None:
                        continue
                    if duration is not None and snapped >= int(duration):
                        continue
                    if last_start is not None and snapped <= last_start:
                        next_idx = bisect.bisect_right(rounded_cue_starts, last_start)
                        if next_idx >= len(rounded_cue_starts):
                            continue
                        snapped = rounded_cue_starts[next_idx]
                    if snapped in used_seconds:
                        continue
                    items.append((title, float(snapped)))
                    used_seconds.add(snapped)
                    last_start = snapped
                    if len(items) >= 10:
                        break
        except Exception:
            items = []
        if 5 <= len(items) <= 10:
            # Filter out generic titles
            generic = {"introduction", "overview", "conclusion", "finale", "final thoughts", "summary"}
            items = [(t, s) for (t, s) in items if t.strip().lower() not in generic]
            return _postprocess_chapters(items, duration)
        # Retry once with harsher system if parse failed or count out of bounds
        ai2 = None
        for i in range(2):
            ai2 = _call_openai(
                prompt,
                system='Return ONLY JSON: {"chapters": []}. If format invalid, output exactly {"chapters": []}',
                max_tokens=500,
                presence_penalty=0.0,
                frequency_penalty=0.0,
                top_p=0.0,
                response_format={"type": "json_object"},
            )
            if ai2:
                break
            time.sleep(0.5 * (2 ** i))
        items = []
        try:
            if ai2:
                m2 = re.search(r"\{.*\}", ai2, re.S)
                if m2:
                    data2 = json.loads(m2.group(0))
                    chapters_json2 = data2.get("chapters", []) or []
                    used_seconds2: set[int] = set()
                    last_start2: int | None = None
                    for c in chapters_json2:
                        raw_title2 = str(c.get("title", ""))
                        title2 = _sanitize_title(raw_title2)
                        try:
                            sec_int2 = int(c.get("start", 0))
                        except Exception:
                            continue
                        snapped2 = _snap_to_cue_seconds(sec_int2)
                        if snapped2 is None:
                            continue
                        if duration is not None and snapped2 >= int(duration):
                            continue
                        if last_start2 is not None and snapped2 <= last_start2:
                            next_idx2 = bisect.bisect_right(rounded_cue_starts, last_start2)
                            if next_idx2 >= len(rounded_cue_starts):
                                continue
                            snapped2 = rounded_cue_starts[next_idx2]
                        if snapped2 in used_seconds2:
                            continue
                        items.append((title2, float(snapped2)))
                        used_seconds2.add(snapped2)
                        last_start2 = snapped2
                        if len(items) >= 10:
                            break
        except Exception:
            items = []
        if 5 <= len(items) <= 10:
            return _postprocess_chapters(items, duration)

    # Fallback to text-based
    text = " ".join(getattr(seg, "text", "") for seg in segments)
    fallback_duration = float(getattr(segments[-1], "end", 0.0)) if segments else duration
    return chapters(text, fallback_duration)

def takeaways(text: str) -> List[str]:
    text_clip = _token_clip(text, max_tokens=3000)
    system = 'Return ONLY JSON: {"takeaways":["...", "..."]}'
    user = (
        '{"task":"takeaways","rules":['
        '"concise","actionable","5-10",'
        '"each_uses_a_verb",'
        '"prefer_specifics_numbers_examples",'
        '"no_restatements","no_fluff"]}\n' + text_clip
    )
    ai = None
    for i in range(2):
        ai = _call_openai(
            user,
            system=system,
            max_tokens=400,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            top_p=0.0,
            response_format={"type": "json_object"},
        )
        if ai:
            break
        time.sleep(0.5 * (2 ** i))
    if ai:
        try:
            data = _safe_json(ai)
            if data is not None:
                out = [re.sub(r"\s+", " ", str(x)).strip() for x in (data.get("takeaways", []) or [])]
                return [x for x in out if x]
        except Exception:
            pass
        # Retry with harsher system
        ai2 = None
        for i in range(2):
            ai2 = _call_openai(
                user,
                system='Return ONLY JSON: {"takeaways": []}. If format invalid, output exactly {"takeaways": []}',
                max_tokens=300,
                presence_penalty=0.0,
                frequency_penalty=0.0,
                top_p=0.0,
                response_format={"type": "json_object"},
            )
            if ai2:
                break
            time.sleep(0.5 * (2 ** i))
        if ai2:
            try:
                data2 = _safe_json(ai2)
                if data2 is not None:
                    out2 = [re.sub(r"\s+", " ", str(x)).strip() for x in (data2.get("takeaways", []) or [])]
                    clean = [x for x in out2 if x]
                    if clean:
                        return clean
            except Exception:
                pass
    return [p.capitalize() for p in extract_keyphrases(text, 8)]


def answer(text: str, question: str) -> str:
    prompt = (
        f"Answer the question based only on the transcript. If unknown, say you don't know.\nQ: {question}\nTranscript:\n" + text[:16000]
    )
    ai = _call_openai(prompt, system="Grounded QA on transcript only")
    if ai:
        return ai
    # fallback: naive search
    q_words = set(re.findall(r"\w+", question.lower()))
    best = ""
    best_score = 0
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s_words = set(re.findall(r"\w+", sentence.lower()))
        score = len(q_words & s_words)
        if score > best_score:
            best = sentence
            best_score = score
    return best or "I don't know."


def entities(text: str) -> List[str]:
    text_clip = _token_clip(text, max_tokens=3200)
    system = 'Return ONLY JSON: {"entities":["...", "..."]}'
    user = '{"task":"entities","rules":["dedupe","flat-list"]}\n' + text_clip
    ai = None
    for i in range(2):
        ai = _call_openai(
            user,
            system=system,
            max_tokens=500,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            top_p=0.0,
            response_format={"type": "json_object"},
        )
        if ai:
            break
        time.sleep(0.5 * (2 ** i))
    if ai:
        try:
            data = _safe_json(ai)
            if data is not None:
                items = [re.sub(r"\s+", " ", str(i)).strip() for i in (data.get("entities", []) or [])]
                seen = set()
                out = []
                for i in items:
                    k = i.lower()
                    if k and k not in seen:
                        seen.add(k)
                        out.append(i)
                return out
        except Exception:
            pass
    # fallback: heuristic proper-noun detection
    candidates = re.findall(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\b", text)
    uniq = []
    seen = set()
    for c in candidates:
        k = c.lower()
        if k not in seen and len(c) > 2:
            seen.add(k)
            uniq.append(c)
    return uniq[:20]


def entities_by_type(text: str) -> dict[str, List[str]]:
    """Return categorized entities: people, organizations, products.

    Tries OpenAI first; falls back to heuristic categorization.
    """
    text_clip = _token_clip(text, max_tokens=3200)
    prompt = (
        '{"task":"entities_by_type","rules":['
        '"dedupe","from_transcript_only",'
        '"include_fictional_npcs_and_factions",'
        '"products_include_vehicles_weapons_tools",'
        '"people_include_usernames_handles"],'
        '"schema":{"people":[],"organizations":[],"products":[]}}\n' + text_clip
    )
    ai = None
    for i in range(2):
        ai = _call_openai(
            prompt,
            system='Return ONLY JSON: {"people":[],"organizations":[],"products":[]}',
            max_tokens=600,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            top_p=0.0,
            response_format={"type": "json_object"},
        )
        if ai:
            break
        time.sleep(0.5 * (2 ** i))
    people: List[str] = []
    orgs: List[str] = []
    products: List[str] = []
    if ai:
        try:
            data = _safe_json(ai)
            if data is not None:
                def _norm_list(x: Any) -> List[str]:
                    return [re.sub(r"\s+", " ", str(i)).strip(" -•") for i in (x or []) if str(i).strip()]
                people.extend(_norm_list(data.get("people")))
                orgs.extend(_norm_list(data.get("organizations")))
                products.extend(_norm_list(data.get("products")))
        except Exception:
            pass
    if not (people or orgs or products):
        flat = entities(text)
        org_keywords = [
            "inc", "llc", "ltd", "corp", "company", "network", "studios", "pictures", "discovery",
            "netflix", "disney", "hbo", "warner", "paramount", "cartoon network", "google", "microsoft", "openai"
        ]
        for e in flat:
            lower = e.lower()
            if any(k in lower for k in org_keywords):
                if e not in orgs:
                    orgs.append(e)
            elif " " in e and all(part and part[0].isupper() for part in e.split()[:2]):
                if e not in people:
                    people.append(e)
            else:
                if e not in products:
                    products.append(e)
    # Deduplicate while preserving order
    def dedup(seq: List[str]) -> List[str]:
        seen: set[str] = set()
        out: List[str] = []
        for s in seq:
            k = re.sub(r"\s+", " ", s.strip())
            kl = k.lower()
            if kl and kl not in seen:
                seen.add(kl)
                out.append(k)
        return out
    return {
        "people": dedup(people)[:20],
        "organizations": dedup(orgs)[:20],
        "products": dedup(products)[:20],
    }


def grounded_chat(text: str, messages: List[dict[str, str]], max_chars: int = 16000) -> str:
    """Perform grounded chat limited to the transcript content and provided history.

    - Truncates transcript to max_chars.
    - Includes a strict system instruction to only use the transcript.
    - Accepts prior messages in OpenAI chat format (role, content).
    """
    key = _effective_openai_key()
    system = (
        "You are a helpful assistant. Answer using ONLY the content between <TRANSCRIPT> and </TRANSCRIPT>. "
        "If the answer cannot be found strictly within the transcript, reply with: "
        "'I don't know.'"
    )
    # If no key is available, provide a graceful fallback using QA on last user message.
    user_prompt = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_prompt = m.get("content", "")
            break

    if not key:
        return answer(text, user_prompt) if user_prompt else "I don't know."

    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=key)
        chat_messages = [{"role": "system", "content": system}]
        # Put transcript in a user message with clear delimiters
        transcript_clip = _token_clip(text, max_tokens=3500)
        chat_messages.append({"role": "user", "content": f"<TRANSCRIPT>\n{transcript_clip}\n</TRANSCRIPT>"})
        chat_messages.extend(messages[-10:])  # bound history to last 10 (after transcript)
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=chat_messages,  # type: ignore[arg-type]
            temperature=0.2,
            presence_penalty=0.0,
            frequency_penalty=0.0,
            max_tokens=800,
        )
        out = resp.choices[0].message.content  # type: ignore[assignment]
        return out or ""
    except Exception:
        # Fallback to simple grounded QA
        return answer(text, user_prompt) if user_prompt else "I don't know."

