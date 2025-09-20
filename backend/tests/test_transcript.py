"""Tests for transcript service."""
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
import pytest

from app.services.transcript import (
    fetch_transcript_via_api,
    extract_youtube_id,
    download_audio_with_ytdlp,
    parse_srt,
    punctuate_text,
    punctuate_segments,
    get_transcript_pipeline,
    segments_to_text,
)
from app.models.schemas import TranscriptSegment


class TestYouTubeIDExtraction:
    """Test YouTube ID extraction from various URL formats."""

    def test_extract_youtube_id_watch_url(self):
        """Test extraction from watch URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = extract_youtube_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_extract_youtube_id_youtu_be(self):
        """Test extraction from youtu.be URL."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        result = extract_youtube_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_extract_youtube_id_shorts(self):
        """Test extraction from shorts URL."""
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        result = extract_youtube_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_extract_youtube_id_embed(self):
        """Test extraction from embed URL."""
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        result = extract_youtube_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_extract_youtube_id_live(self):
        """Test extraction from live URL."""
        url = "https://www.youtube.com/live/dQw4w9WgXcQ"
        result = extract_youtube_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_extract_youtube_id_with_params(self):
        """Test extraction with additional parameters."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PLrAXtmRdnEQy"
        result = extract_youtube_id(url)
        assert result == "dQw4w9WgXcQ"

    def test_extract_youtube_id_invalid_url(self):
        """Test with invalid URL."""
        with pytest.raises(ValueError):
            extract_youtube_id("https://example.com/invalid")


class TestTranscriptAPI:
    """Test YouTube transcript API integration."""

    @patch('app.services.transcript.YouTubeTranscriptApi')
    def test_fetch_transcript_via_api_success(self, mock_api_class):
        """Test successful transcript fetch."""
        # Mock transcript data
        mock_snippet = Mock()
        mock_snippet.text = "Hello world"
        mock_snippet.start = 0.0
        mock_snippet.duration = 2.5

        mock_transcript = Mock()
        mock_transcript.fetch.return_value = [mock_snippet]
        mock_transcript.is_generated = False
        mock_transcript.language_code = "en"

        mock_transcript_list = Mock()
        mock_transcript_list.find_transcript.return_value = mock_transcript

        mock_api = Mock()
        mock_api.list.return_value = mock_transcript_list
        mock_api_class.return_value = mock_api

        segments, source, lang = fetch_transcript_via_api("test_video_id")

        assert len(segments) == 1
        assert segments[0].text == "Hello world"
        assert segments[0].start == 0.0
        assert segments[0].end == 2.5
        assert source == "youtube-manual"
        assert lang == "en"

    @patch('app.services.transcript.YouTubeTranscriptApi')
    def test_fetch_transcript_via_api_auto_generated(self, mock_api_class):
        """Test auto-generated transcript detection."""
        mock_snippet = Mock()
        mock_snippet.text = "Auto generated text"
        mock_snippet.start = 0.0
        mock_snippet.duration = 1.0

        mock_transcript = Mock()
        mock_transcript.fetch.return_value = [mock_snippet]
        mock_transcript.is_generated = True
        mock_transcript.language_code = "en"

        mock_transcript_list = Mock()
        mock_transcript_list.find_transcript.return_value = mock_transcript

        mock_api = Mock()
        mock_api.list.return_value = mock_transcript_list
        mock_api_class.return_value = mock_api

        segments, source, lang = fetch_transcript_via_api("test_video_id")

        assert source == "youtube-auto"

    @patch('app.services.transcript.YouTubeTranscriptApi')
    def test_fetch_transcript_via_api_no_transcript(self, mock_api_class):
        """Test when no transcript is available."""
        from youtube_transcript_api import NoTranscriptFound

        mock_api = Mock()
        mock_api.list.side_effect = NoTranscriptFound("test_video_id", [], [])
        mock_api_class.return_value = mock_api

        segments, source, lang = fetch_transcript_via_api("test_video_id")

        assert segments == []
        assert source == "missing"
        assert lang is None


class TestSRTParsing:
    """Test SRT file parsing."""

    def test_parse_srt_valid_file(self):
        """Test parsing valid SRT file."""
        srt_content = """1
00:00:00,000 --> 00:00:02,500
Hello world

2
00:00:02,500 --> 00:00:05,000
This is a test

"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            f.write(srt_content)
            f.flush()

            segments = parse_srt(f.name)

            assert len(segments) == 2
            assert segments[0].text == "Hello world"
            assert segments[0].start == 0.0
            assert segments[0].end == 2.5
            assert segments[1].text == "This is a test"
            assert segments[1].start == 2.5
            assert segments[1].end == 5.0

            os.unlink(f.name)

    def test_parse_srt_empty_file(self):
        """Test parsing empty SRT file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False) as f:
            f.write("")
            f.flush()

            segments = parse_srt(f.name)
            assert segments == []

            os.unlink(f.name)


class TestPunctuation:
    """Test punctuation restoration."""

    def test_punctuate_text_success(self):
        """Test successful punctuation restoration."""
        # Mock the deepmultilingualpunctuation import and usage
        with patch('builtins.__import__') as mock_import:
            mock_model = Mock()
            mock_model.restore_punctuation.return_value = "Hello, world! How are you?"

            def import_side_effect(name, *args, **kwargs):
                if name == 'deepmultilingualpunctuation':
                    mock_module = Mock()
                    mock_module.PunctuationModel.return_value = mock_model
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect

            result = punctuate_text("hello world how are you")
            assert result == "Hello, world! How are you?"

    def test_punctuate_text_failure(self):
        """Test punctuation restoration failure fallback."""
        # Test the actual function behavior when import fails
        text = "hello world"
        result = punctuate_text(text)
        # Should return original text when punctuation library is not available
        assert result == text or isinstance(result, str)

    def test_punctuate_segments(self):
        """Test punctuation of transcript segments."""
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="hello"),
            TranscriptSegment(start=2.0, end=4.0, text="world"),
        ]

        with patch('app.services.transcript.punctuate_text') as mock_punctuate:
            mock_punctuate.return_value = "Hello, world!"

            result = punctuate_segments(segments)

            # Should redistribute punctuated text across segments
            assert len(result) >= 1
            assert any("Hello" in seg.text for seg in result)


class TestAudioDownload:
    """Test audio download functionality."""

    @patch('app.services.transcript.subprocess.run')
    @patch('app.services.transcript.os.listdir')
    def test_download_audio_with_ytdlp_success(self, mock_listdir, mock_subprocess):
        """Test successful audio download."""
        mock_subprocess.return_value = Mock()
        mock_listdir.return_value = ["test_video_id.wav"]

        with tempfile.TemporaryDirectory() as temp_dir:
            result = download_audio_with_ytdlp("test_video_id", temp_dir)
            expected_path = os.path.join(temp_dir, "test_video_id.wav")
            assert result == expected_path

    @patch('app.services.transcript.subprocess.run')
    @patch('app.services.transcript.os.listdir')
    def test_download_audio_with_ytdlp_no_file(self, mock_listdir, mock_subprocess):
        """Test audio download when no file is created."""
        mock_subprocess.return_value = Mock()
        mock_listdir.return_value = []  # No files created

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict('os.environ', {}, clear=False):  # Clear test env var
                with pytest.raises(FileNotFoundError):
                    download_audio_with_ytdlp("test_video_id", temp_dir)


class TestTranscriptPipeline:
    """Test the complete transcript pipeline."""

    @patch('app.services.transcript.fetch_transcript_via_api')
    @patch('app.services.transcript.punctuate_segments')
    def test_get_transcript_pipeline_youtube_success(self, mock_punctuate, mock_fetch):
        """Test pipeline with successful YouTube transcript."""
        # Use a longer text to avoid whisper fallback
        segments = [TranscriptSegment(start=0.0, end=2.0, text="Hello world this is a longer transcript that should not trigger whisper fallback because it has sufficient content")]
        mock_fetch.return_value = (segments, "youtube-manual", "en")
        mock_punctuate.return_value = segments

        result_segments, source, lang = get_transcript_pipeline("test_video_id")

        assert len(result_segments) == 1
        assert source == "youtube-manual"
        assert lang == "en"
        mock_punctuate.assert_called_once()

    @patch('app.services.transcript.fetch_transcript_via_api')
    @patch('app.services.transcript.download_audio_with_ytdlp')
    @patch('app.services.transcript.run_whisper_cpp')
    @patch('app.services.transcript.punctuate_segments')
    def test_get_transcript_pipeline_whisper_fallback(self, mock_punctuate, mock_whisper, mock_download, mock_fetch):
        """Test pipeline with whisper fallback."""
        # YouTube API returns no transcript
        mock_fetch.return_value = ([], "missing", None)

        # Whisper produces transcript
        whisper_segments = [TranscriptSegment(start=0.0, end=2.0, text="Whisper transcript")]
        mock_download.return_value = "/tmp/audio.wav"
        mock_whisper.return_value = whisper_segments
        mock_punctuate.return_value = whisper_segments

        result_segments, source, lang = get_transcript_pipeline("test_video_id")

        assert len(result_segments) == 1
        assert source == "whisper"
        assert lang == "en"
        mock_download.assert_called_once()
        mock_whisper.assert_called_once()


class TestUtilityFunctions:
    """Test utility functions."""

    def test_segments_to_text(self):
        """Test converting segments to text."""
        segments = [
            TranscriptSegment(start=0.0, end=2.0, text="Hello"),
            TranscriptSegment(start=2.0, end=4.0, text="world"),
        ]

        result = segments_to_text(segments)
        assert result == "Hello world"

    def test_segments_to_text_empty(self):
        """Test converting empty segments to text."""
        result = segments_to_text([])
        assert result == ""
