from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str


class TranscriptResponse(BaseModel):
    video_id: str
    source: str
    language: Optional[str] = None
    segments: List[TranscriptSegment]
    text: str


class VideoMeta(BaseModel):
    video_id: str
    title: str
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    channel: Optional[str] = None
    duration: Optional[float] = None


class SummaryResponse(BaseModel):
    video_id: str
    summary: str


class ChapterItem(BaseModel):
    title: str
    start: float


class ChaptersResponse(BaseModel):
    video_id: str
    chapters: List[ChapterItem]


class TakeawaysResponse(BaseModel):
    video_id: str
    takeaways: List[str]


class QARequest(BaseModel):
    video_id: str
    question: str


class QAResponse(BaseModel):
    video_id: str
    question: str
    answer: str


class EntitiesResponse(BaseModel):
    video_id: str
    entities: List[str]


# Chat models
class ChatMessage(BaseModel):
    role: str = Field(..., description="one of system|user|assistant")
    content: str


class ChatRequest(BaseModel):
    video_id: str
    messages: List[ChatMessage] = Field(
        default_factory=list,
        description="Prior chat history; newest last. The last message should be the user's prompt.",
    )


class ChatResponse(BaseModel):
    video_id: str
    message: ChatMessage

