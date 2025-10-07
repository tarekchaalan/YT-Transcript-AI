from __future__ import annotations

import os
import contextvars
import re
from typing import List, Optional

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


def _call_openai(prompt: str, system: str = "You are a helpful assistant.") -> Optional[str]:
    key = _effective_openai_key()
    if not key:
        return None
    try:
        # Create a short-lived client with the effective key to avoid cross-request leakage
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content  # type: ignore[return-value]
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


def extract_keyphrases(text: str, max_phrases: int = 12) -> List[str]:
    kw = yake.KeywordExtractor(
        top=max_phrases * 2,  # Get more candidates
        n=3,  # Up to 3-word phrases
        stopwords=None,  # Use default English stopwords
        dedupLim=0.7,  # Remove near-duplicates
        windowsSize=2
    )
    candidates = kw.extract_keywords(text)

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
    prompt = (
        "Summarize the following transcript in 5-8 concise bullet points. \n" + text[:16000]
    )
    ai = _call_openai(prompt, system="Expert concise summarizer")
    if ai:
        return ai

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
    prompt = (
        "Create 5-10 chapter titles with start times in seconds as 'title|start'. "
        "Only output one per line. Transcript:"\
        + text[:16000]
    )
    ai = _call_openai(prompt, system="You generate chapter outlines with timestamps")
    if ai:
        items = []
        for line in ai.splitlines():
            if "|" in line:
                t, s = line.split("|", 1)
                try:
                    items.append((t.strip("- •"), float(s.strip())))
                except Exception:
                    continue
        if items:
            return items
    # fallback: evenly spaced chapters titled by keyphrases
    num = 8
    if duration and duration > 0:
        interval = duration / num
    else:
        interval = 120.0
    phrases = extract_keyphrases(text, num)
    return [(phrases[i] if i < len(phrases) else f"Chapter {i+1}", i * interval) for i in range(num)]


def takeaways(text: str) -> List[str]:
    prompt = "List the 5-10 most important actionable takeaways from the transcript." + text[:16000]
    ai = _call_openai(prompt, system="You produce crisp, numbered takeaways")
    if ai:
        lines = [re.sub(r"^[-*\d.\)\s]+", "", l).strip() for l in ai.splitlines() if l.strip()]
        return [l for l in lines if l]
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
    prompt = "Extract and deduplicate named entities (people, orgs, products) as a list." + text[:16000]
    ai = _call_openai(prompt, system="Entity extraction and deduplication")
    if ai:
        items = [re.sub(r"^[-*\d.\)\s]+", "", l).strip() for l in ai.splitlines() if l.strip()]
        items = [re.sub(r"\s+", " ", i) for i in items]
        seen = set()
        out = []
        for i in items:
            k = i.lower()
            if k not in seen:
                seen.add(k)
                out.append(i)
        return out
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
    prompt = (
        "Extract named entities from the transcript and categorize into People, Organizations, Products.\n"
        "Return as lines in the form 'People: name1; name2' etc.\n"
        + text[:16000]
    )
    ai = _call_openai(prompt, system="You extract entities and categorize them clearly")
    people: List[str] = []
    orgs: List[str] = []
    products: List[str] = []
    if ai:
        try:
            for line in ai.splitlines():
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                items = [re.sub(r"\s+", " ", i).strip(" -•") for i in re.split(r"[,;]", v) if i.strip()]
                if k.strip().lower().startswith("people"):
                    people.extend(items)
                elif k.strip().lower().startswith("org"):
                    orgs.extend(items)
                elif k.strip().lower().startswith("prod"):
                    products.extend(items)
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
        "You are a helpful assistant. You must answer ONLY based on the provided transcript. "
        "If the answer cannot be derived from the transcript, say you don't know. Be concise."
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
        chat_messages.extend(messages[-10:])  # bound history to last 10
        chat_messages.append({
            "role": "system",
            "content": "Transcript (truncated):\n" + text[:max_chars],
        })
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=chat_messages,  # type: ignore[arg-type]
            temperature=0.2,
        )
        out = resp.choices[0].message.content  # type: ignore[assignment]
        return out or ""
    except Exception:
        # Fallback to simple grounded QA
        return answer(text, user_prompt) if user_prompt else "I don't know."

