"""Tests for data models."""
import pytest
from pydantic import ValidationError

from app.models.schemas import (
    TranscriptSegment,
    TranscriptResponse,
    VideoMeta,
    SummaryResponse,
    ChapterItem,
    ChaptersResponse,
    TakeawaysResponse,
    QARequest,
    QAResponse,
    EntitiesResponse,
)


class TestTranscriptSegment:
    """Test TranscriptSegment model."""

    def test_transcript_segment_valid(self):
        """Test valid transcript segment."""
        segment = TranscriptSegment(
            start=0.0,
            end=2.5,
            text="Hello world"
        )
        assert segment.start == 0.0
        assert segment.end == 2.5
        assert segment.text == "Hello world"

    def test_transcript_segment_invalid_start(self):
        """Test invalid start time."""
        with pytest.raises(ValidationError):
            TranscriptSegment(
                start="invalid",
                end=2.5,
                text="Hello world"
            )

    def test_transcript_segment_negative_time(self):
        """Test negative time values."""
        # Should allow negative start (though unusual)
        segment = TranscriptSegment(
            start=-1.0,
            end=2.5,
            text="Hello world"
        )
        assert segment.start == -1.0


class TestTranscriptResponse:
    """Test TranscriptResponse model."""

    def test_transcript_response_valid(self):
        """Test valid transcript response."""
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="Hello"),
            TranscriptSegment(start=2.0, end=4.0, text="world"),
        ]

        response = TranscriptResponse(
            video_id="test123",
            source="youtube-auto",
            language="en",
            segments=segments,
            text="Hello world"
        )

        assert response.video_id == "test123"
        assert response.source == "youtube-auto"
        assert response.language == "en"
        assert len(response.segments) == 2
        assert response.text == "Hello world"

    def test_transcript_response_optional_fields(self):
        """Test transcript response with optional fields."""
        response = TranscriptResponse(
            video_id="test123",
            source="whisper",
            segments=[],
            text=""
        )

        assert response.language is None


class TestVideoMeta:
    """Test VideoMeta model."""

    def test_video_meta_complete(self):
        """Test complete video metadata."""
        meta = VideoMeta(
            video_id="test123",
            title="Test Video",
            description="A test video",
            thumbnail_url="https://example.com/thumb.jpg",
            channel="Test Channel",
            duration=300.5
        )

        assert meta.video_id == "test123"
        assert meta.title == "Test Video"
        assert meta.duration == 300.5

    def test_video_meta_minimal(self):
        """Test minimal video metadata."""
        meta = VideoMeta(
            video_id="test123",
            title="Test Video"
        )

        assert meta.video_id == "test123"
        assert meta.title == "Test Video"
        assert meta.description is None
        assert meta.thumbnail_url is None
        assert meta.channel is None
        assert meta.duration is None


class TestSummaryResponse:
    """Test SummaryResponse model."""

    def test_summary_response_valid(self):
        """Test valid summary response."""
        response = SummaryResponse(
            video_id="test123",
            summary="This is a summary of the video content."
        )

        assert response.video_id == "test123"
        assert response.summary == "This is a summary of the video content."


class TestChapterItem:
    """Test ChapterItem model."""

    def test_chapter_item_valid(self):
        """Test valid chapter item."""
        chapter = ChapterItem(
            title="Introduction",
            start=0.0
        )

        assert chapter.title == "Introduction"
        assert chapter.start == 0.0

    def test_chapter_item_invalid_start(self):
        """Test invalid start time."""
        with pytest.raises(ValidationError):
            ChapterItem(
                title="Introduction",
                start="invalid"
            )


class TestChaptersResponse:
    """Test ChaptersResponse model."""

    def test_chapters_response_valid(self):
        """Test valid chapters response."""
        chapters = [
            ChapterItem(title="Introduction", start=0.0),
            ChapterItem(title="Main Content", start=120.0),
            ChapterItem(title="Conclusion", start=240.0),
        ]

        response = ChaptersResponse(
            video_id="test123",
            chapters=chapters
        )

        assert response.video_id == "test123"
        assert len(response.chapters) == 3
        assert response.chapters[0].title == "Introduction"

    def test_chapters_response_empty(self):
        """Test chapters response with empty chapters."""
        response = ChaptersResponse(
            video_id="test123",
            chapters=[]
        )

        assert len(response.chapters) == 0


class TestTakeawaysResponse:
    """Test TakeawaysResponse model."""

    def test_takeaways_response_valid(self):
        """Test valid takeaways response."""
        takeaways = [
            "First key takeaway",
            "Second important point",
            "Third valuable insight"
        ]

        response = TakeawaysResponse(
            video_id="test123",
            takeaways=takeaways
        )

        assert response.video_id == "test123"
        assert len(response.takeaways) == 3
        assert "First key takeaway" in response.takeaways


class TestQARequest:
    """Test QARequest model."""

    def test_qa_request_valid(self):
        """Test valid Q&A request."""
        request = QARequest(
            video_id="test123",
            question="What is this video about?"
        )

        assert request.video_id == "test123"
        assert request.question == "What is this video about?"

    def test_qa_request_empty_question(self):
        """Test Q&A request with empty question."""
        request = QARequest(
            video_id="test123",
            question=""
        )

        assert request.question == ""


class TestQAResponse:
    """Test QAResponse model."""

    def test_qa_response_valid(self):
        """Test valid Q&A response."""
        response = QAResponse(
            video_id="test123",
            question="What is this video about?",
            answer="This video explains machine learning concepts."
        )

        assert response.video_id == "test123"
        assert response.question == "What is this video about?"
        assert response.answer == "This video explains machine learning concepts."


class TestEntitiesResponse:
    """Test EntitiesResponse model."""

    def test_entities_response_valid(self):
        """Test valid entities response."""
        entities = ["Google", "Microsoft", "OpenAI", "Python"]

        response = EntitiesResponse(
            video_id="test123",
            entities=entities
        )

        assert response.video_id == "test123"
        assert len(response.entities) == 4
        assert "Google" in response.entities

    def test_entities_response_empty(self):
        """Test entities response with no entities."""
        response = EntitiesResponse(
            video_id="test123",
            entities=[]
        )

        assert len(response.entities) == 0


class TestModelValidation:
    """Test model validation edge cases."""

    def test_video_id_validation(self):
        """Test video ID validation across models."""
        # Test that empty video ID is allowed
        response = SummaryResponse(
            video_id="",
            summary="Test summary"
        )
        assert response.video_id == ""

        # Test special characters in video ID
        response = SummaryResponse(
            video_id="test-123_ABC",
            summary="Test summary"
        )
        assert response.video_id == "test-123_ABC"

    def test_text_field_validation(self):
        """Test text field validation."""
        # Test unicode text
        segment = TranscriptSegment(
            start=0.0,
            end=2.0,
            text="Hello 世界 🌍"
        )
        assert segment.text == "Hello 世界 🌍"

        # Test very long text
        long_text = "A" * 10000
        segment = TranscriptSegment(
            start=0.0,
            end=2.0,
            text=long_text
        )
        assert len(segment.text) == 10000
