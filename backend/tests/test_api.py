"""Tests for API routes."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

from app.main import app
from app.models.schemas import TranscriptSegment


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_transcript_segments():
    """Mock transcript segments for testing."""
    return [
        TranscriptSegment(start=0.0, end=2.0, text="Hello world"),
        TranscriptSegment(start=2.0, end=4.0, text="This is a test"),
        TranscriptSegment(start=4.0, end=6.0, text="Thank you"),
    ]


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health check returns OK."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestParseEndpoint:
    """Test URL parsing endpoint."""

    def test_parse_valid_youtube_url(self, client):
        """Test parsing valid YouTube URL."""
        response = client.post("/parse", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
        assert response.status_code == 200
        assert response.json() == {"video_id": "dQw4w9WgXcQ"}

    def test_parse_youtu_be_url(self, client):
        """Test parsing youtu.be URL."""
        response = client.post("/parse", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
        assert response.status_code == 200
        assert response.json() == {"video_id": "dQw4w9WgXcQ"}

    def test_parse_invalid_url(self, client):
        """Test parsing invalid URL."""
        response = client.post("/parse", json={"url": "https://example.com/invalid"})
        assert response.status_code == 400
        assert "detail" in response.json()


class TestTranscriptEndpoint:
    """Test transcript endpoint."""

    @patch('app.api.routes.get_transcript_pipeline')
    def test_get_transcript_success(self, mock_pipeline, client, mock_transcript_segments):
        """Test successful transcript retrieval."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")

        response = client.get("/api/transcript/test_video_id")
        assert response.status_code == 200

        data = response.json()
        assert data["video_id"] == "test_video_id"
        assert data["source"] == "youtube-auto"
        assert data["language"] == "en"
        assert len(data["segments"]) == 3
        assert data["segments"][0]["text"] == "Hello world"
        assert "Hello world This is a test Thank you" in data["text"]

    @patch('app.api.routes.get_transcript_pipeline')
    def test_get_transcript_not_available(self, mock_pipeline, client):
        """Test transcript not available."""
        mock_pipeline.return_value = ([], "missing", None)

        response = client.get("/api/transcript/test_video_id")
        assert response.status_code == 404
        assert response.json()["detail"] == "Transcript not available"


class TestSummaryEndpoint:
    """Test summary endpoint."""

    @patch('app.api.routes.get_transcript_pipeline')
    @patch('app.api.routes.summarize')
    def test_get_summary_success(self, mock_summarize, mock_pipeline, client, mock_transcript_segments):
        """Test successful summary generation."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")
        mock_summarize.return_value = "• Key point 1\n• Key point 2"

        response = client.get("/api/summary/test_video_id")
        assert response.status_code == 200

        data = response.json()
        assert data["video_id"] == "test_video_id"
        assert data["summary"] == "• Key point 1\n• Key point 2"

    @patch('app.api.routes.get_transcript_pipeline')
    def test_get_summary_no_transcript(self, mock_pipeline, client):
        """Test summary when no transcript available."""
        mock_pipeline.return_value = ([], "missing", None)

        response = client.get("/api/summary/test_video_id")
        assert response.status_code == 404


class TestChaptersEndpoint:
    """Test chapters endpoint."""

    @patch('app.api.routes.get_transcript_pipeline')
    @patch('app.api.routes.ai_chapters')
    def test_get_chapters_success(self, mock_chapters, mock_pipeline, client, mock_transcript_segments):
        """Test successful chapters generation."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")
        mock_chapters.return_value = [("Introduction", 0.0), ("Main Content", 120.0), ("Conclusion", 240.0)]

        response = client.get("/api/chapters/test_video_id")
        assert response.status_code == 200

        data = response.json()
        assert data["video_id"] == "test_video_id"
        assert len(data["chapters"]) == 3
        assert data["chapters"][0]["title"] == "Introduction"
        assert data["chapters"][0]["start"] == 0.0


class TestTakeawaysEndpoint:
    """Test takeaways endpoint."""

    @patch('app.api.routes.get_transcript_pipeline')
    @patch('app.api.routes.ai_takeaways')
    def test_get_takeaways_success(self, mock_takeaways, mock_pipeline, client, mock_transcript_segments):
        """Test successful takeaways generation."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")
        mock_takeaways.return_value = ["Key takeaway 1", "Key takeaway 2", "Key takeaway 3"]

        response = client.get("/api/takeaways/test_video_id")
        assert response.status_code == 200

        data = response.json()
        assert data["video_id"] == "test_video_id"
        assert len(data["takeaways"]) == 3
        assert "Key takeaway 1" in data["takeaways"]


class TestQAEndpoint:
    """Test Q&A endpoint."""

    @patch('app.api.routes.get_transcript_pipeline')
    @patch('app.api.routes.ai_answer')
    def test_post_qa_success(self, mock_answer, mock_pipeline, client, mock_transcript_segments):
        """Test successful Q&A."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")
        mock_answer.return_value = "This is the answer to your question."

        response = client.post("/api/qa", json={
            "video_id": "test_video_id",
            "question": "What is this about?"
        })
        assert response.status_code == 200

        data = response.json()
        assert data["video_id"] == "test_video_id"
        assert data["question"] == "What is this about?"
        assert data["answer"] == "This is the answer to your question."


class TestEntitiesEndpoint:
    """Test entities endpoint."""

    @patch('app.api.routes.get_transcript_pipeline')
    @patch('app.api.routes.ai_entities')
    def test_get_entities_success(self, mock_entities, mock_pipeline, client, mock_transcript_segments):
        """Test successful entities extraction."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")
        mock_entities.return_value = ["Google", "Microsoft", "OpenAI"]

        response = client.get("/api/entities/test_video_id")
        assert response.status_code == 200

        data = response.json()
        assert data["video_id"] == "test_video_id"
        assert len(data["entities"]) == 3
        assert "Google" in data["entities"]


class TestExportEndpoints:
    """Test export endpoints."""

    @patch('app.api.routes.get_transcript_pipeline')
    def test_export_txt(self, mock_pipeline, client, mock_transcript_segments):
        """Test TXT export."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")

        response = client.get("/api/export/txt/test_video_id")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "Hello world This is a test Thank you" in response.text

    @patch('app.api.routes.get_transcript_pipeline')
    def test_export_srt(self, mock_pipeline, client, mock_transcript_segments):
        """Test SRT export."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")

        response = client.get("/api/export/srt/test_video_id")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "00:00:00,000 --> 00:00:02,000" in response.text
        assert "Hello world" in response.text

    @patch('app.api.routes.get_transcript_pipeline')
    def test_export_vtt(self, mock_pipeline, client, mock_transcript_segments):
        """Test VTT export."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")

        response = client.get("/api/export/vtt/test_video_id")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "WEBVTT" in response.text
        assert "00:00:00.000 --> 00:00:02.000" in response.text

    @patch('app.api.routes.get_transcript_pipeline')
    @patch('app.api.routes.ai_chapters')
    def test_export_chapters(self, mock_chapters, mock_pipeline, client, mock_transcript_segments):
        """Test chapters JSON export."""
        mock_pipeline.return_value = (mock_transcript_segments, "youtube-auto", "en")
        mock_chapters.return_value = [("Introduction", 0.0), ("Conclusion", 120.0)]

        response = client.get("/api/export/chapters/test_video_id")
        assert response.status_code == 200

        data = response.json()
        assert data["video_id"] == "test_video_id"
        assert len(data["chapters"]) == 2


class TestRateLimiting:
    """Test rate limiting functionality."""

    @patch('app.core.limits.limiter.check')
    def test_rate_limit_applied(self, mock_check, client):
        """Test that rate limiting is applied to endpoints."""
        # Rate limit should be checked for all API calls
        response = client.get("/health")
        assert response.status_code == 200
        mock_check.assert_called_once()

    @patch('app.core.limits.limiter.check')
    def test_rate_limit_exceeded(self, mock_check, client):
        """Test rate limit exceeded."""
        from fastapi import HTTPException
        mock_check.side_effect = HTTPException(status_code=429, detail="Too many requests")

        response = client.get("/health")
        assert response.status_code == 429
        assert "Too many requests" in response.json()["detail"]
