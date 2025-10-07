from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import PlainTextResponse, JSONResponse

from app.models.schemas import (
    TranscriptResponse,
    SummaryResponse,
    ChaptersResponse,
    ChapterItem,
    TakeawaysResponse,
    QARequest,
    QAResponse,
    EntitiesResponse,
    ChatRequest,
    ChatResponse,
)
from app.services.transcript import get_transcript_pipeline, segments_to_text
from app.services.ai import summarize, chapters as ai_chapters, takeaways as ai_takeaways, answer as ai_answer, entities as ai_entities
from app.services.ai import grounded_chat
from app.services.ai import override_openai_key_for_request
from app.core.limits import guard_request


router = APIRouter()


@router.get("/transcript/{video_id}", response_model=TranscriptResponse, dependencies=[Depends(guard_request)])
async def get_transcript(video_id: str) -> TranscriptResponse:
    segments, source, lang = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    return TranscriptResponse(
        video_id=video_id,
        source=source,
        language=lang,
        segments=segments,
        text=segments_to_text(segments),
    )


@router.get("/summary/{video_id}", response_model=SummaryResponse, dependencies=[Depends(guard_request)])
async def get_summary(video_id: str, x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key")) -> SummaryResponse:
    segments, source, lang = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    text = segments_to_text(segments)
    with override_openai_key_for_request(x_openai_key):
        return SummaryResponse(video_id=video_id, summary=summarize(text))


@router.get("/chapters/{video_id}", response_model=ChaptersResponse, dependencies=[Depends(guard_request)])
async def get_chapters(video_id: str, x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key")) -> ChaptersResponse:
    segments, source, lang = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    text = segments_to_text(segments)
    duration = segments[-1].end if segments else None
    with override_openai_key_for_request(x_openai_key):
        items = ai_chapters(text, duration)
    # Clamp chapter starts to valid range [0, duration]
    clamped: list[tuple[str, float]] = []
    for t, s in items:
        try:
            s_float = float(s)
        except Exception:
            continue
        if s_float < 0:
            s_float = 0.0
        if duration is not None and s_float > duration:
            s_float = max(0.0, float(duration))
        clamped.append((t, s_float))
    return ChaptersResponse(
        video_id=video_id,
        chapters=[ChapterItem(title=t, start=s) for t, s in clamped],
    )


@router.get("/takeaways/{video_id}", response_model=TakeawaysResponse, dependencies=[Depends(guard_request)])
async def get_takeaways(video_id: str, x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key")) -> TakeawaysResponse:
    segments, source, lang = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    text = segments_to_text(segments)
    with override_openai_key_for_request(x_openai_key):
        return TakeawaysResponse(video_id=video_id, takeaways=ai_takeaways(text))


@router.post("/qa", response_model=QAResponse, dependencies=[Depends(guard_request)])
async def post_qa(req: QARequest, x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key")) -> QAResponse:
    segments, _, _ = get_transcript_pipeline(req.video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    text = segments_to_text(segments)
    with override_openai_key_for_request(x_openai_key):
        return QAResponse(video_id=req.video_id, question=req.question, answer=ai_answer(text, req.question))


@router.get("/entities/{video_id}", response_model=EntitiesResponse, dependencies=[Depends(guard_request)])
async def get_entities(video_id: str, x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key")) -> EntitiesResponse:
    segments, source, lang = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    text = segments_to_text(segments)
    with override_openai_key_for_request(x_openai_key):
        return EntitiesResponse(video_id=video_id, entities=ai_entities(text))


@router.get("/export/txt/{video_id}", response_class=PlainTextResponse, dependencies=[Depends(guard_request)])
async def export_txt(video_id: str):
    segments, source, lang = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    body = segments_to_text(segments)
    return PlainTextResponse(content=body, headers={"Content-Disposition": f"attachment; filename={video_id}.txt"})


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"


@router.get("/export/srt/{video_id}", response_class=PlainTextResponse, dependencies=[Depends(guard_request)])
async def export_srt(video_id: str):
    segments, _, _ = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    lines = []
    for i, seg in enumerate(segments, start=1):
        # Convert seconds to SRT format HH:MM:SS,mmm
        start_h = int(seg.start // 3600)
        start_m = int((seg.start % 3600) // 60)
        start_s = int(seg.start % 60)
        start_ms = int((seg.start % 1) * 1000)

        end_h = int(seg.end // 3600)
        end_m = int((seg.end % 3600) // 60)
        end_s = int(seg.end % 60)
        end_ms = int((seg.end % 1) * 1000)

        lines.append(str(i))
        lines.append(f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d} --> {end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}")
        lines.append(seg.text)
        lines.append("")
    body = "\n".join(lines)
    return PlainTextResponse(content=body, headers={"Content-Disposition": f"attachment; filename={video_id}.srt"})


@router.get("/export/vtt/{video_id}", response_class=PlainTextResponse, dependencies=[Depends(guard_request)])
async def export_vtt(video_id: str):
    segments, _, _ = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    lines = ["WEBVTT", ""]
    for seg in segments:
        sh = _format_timestamp(seg.start)
        eh = _format_timestamp(seg.end)
        lines.append(f"{sh}.000 --> {eh}.000")
        lines.append(seg.text)
        lines.append("")
    body = "\n".join(lines)
    return PlainTextResponse(content=body, headers={"Content-Disposition": f"attachment; filename={video_id}.vtt"})


@router.get("/export/chapters/{video_id}", dependencies=[Depends(guard_request)])
async def export_chapters(video_id: str, x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key")):
    segments, _, _ = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    text = segments_to_text(segments)
    duration = segments[-1].end if segments else None
    with override_openai_key_for_request(x_openai_key):
        items = ai_chapters(text, duration)
    payload = {"video_id": video_id, "chapters": [{"title": t, "start": s} for t, s in items]}
    return JSONResponse(content=payload, headers={"Content-Disposition": f"attachment; filename={video_id}-chapters.json"})


@router.get("/entities/by-type/{video_id}", dependencies=[Depends(guard_request)])
async def get_entities_by_type(video_id: str, x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key")):
    segments, source, lang = get_transcript_pipeline(video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    text = segments_to_text(segments)
    # Try AI categorization if available
    from app.services.ai import entities as ai_entities
    from app.services.ai import entities_by_type as ai_entities_by_type  # type: ignore
    try:
        with override_openai_key_for_request(x_openai_key):
            cats = ai_entities_by_type(text)
    except Exception:
        # Fallback: flat -> simple heuristic categorization
        flat = ai_entities(text)
        people: list[str] = []
        orgs: list[str] = []
        products: list[str] = []
        org_keywords = [
            "inc", "llc", "ltd", "corp", "company", "network", "studios", "pictures", "discovery",
            "netflix", "disney", "hbo", "warner", "paramount", "cartoon network"
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
        cats = {"people": people, "organizations": orgs, "products": products}
    return {"video_id": video_id, **cats}



@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(guard_request)])
async def post_chat(req: ChatRequest, x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key")) -> ChatResponse:
    segments, _, _ = get_transcript_pipeline(req.video_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Transcript not available")
    text = segments_to_text(segments)
    with override_openai_key_for_request(x_openai_key):
        out = grounded_chat(text, [m.dict() for m in req.messages])
    from app.models.schemas import ChatMessage
    return ChatResponse(video_id=req.video_id, message=ChatMessage(role="assistant", content=out))

