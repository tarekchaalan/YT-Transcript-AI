"""Tests for AI service."""
import os
from unittest.mock import Mock, patch
import pytest

from app.services.ai import (
    extract_keyphrases,
    summarize,
    chapters,
    takeaways,
    answer,
    entities,
    _call_openai,
)


class TestKeyphraseExtraction:
    """Test keyphrase extraction."""

    def test_extract_keyphrases_basic(self):
        """Test basic keyphrase extraction."""
        text = "This video discusses artificial intelligence and machine learning algorithms for data science applications."

        phrases = extract_keyphrases(text, max_phrases=5)

        assert isinstance(phrases, list)
        assert len(phrases) <= 5
        # Should extract meaningful multi-word phrases
        assert any(len(phrase.split()) >= 2 for phrase in phrases)

    def test_extract_keyphrases_empty_text(self):
        """Test keyphrase extraction with empty text."""
        phrases = extract_keyphrases("", max_phrases=5)
        assert phrases == []

    def test_extract_keyphrases_filters_stopwords(self):
        """Test that common stopwords are filtered out."""
        text = "The quick brown fox jumps over the lazy dog and runs away."

        phrases = extract_keyphrases(text, max_phrases=10)

        # Should not contain single stopwords
        stopwords = ['the', 'and', 'over', 'away']
        for phrase in phrases:
            assert phrase.lower() not in stopwords


class TestOpenAIIntegration:
    """Test OpenAI API integration."""

    @patch('app.services.ai._openai_client')
    def test_call_openai_success(self, mock_client):
        """Test successful OpenAI API call."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"

        mock_client.chat.completions.create.return_value = mock_response

        result = _call_openai("Test prompt")
        assert result == "Test response"

    @patch('app.services.ai._openai_client')
    def test_call_openai_failure(self, mock_client):
        """Test OpenAI API call failure."""
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        result = _call_openai("Test prompt")
        assert result is None

    @patch('app.services.ai._openai_client', None)
    def test_call_openai_no_client(self):
        """Test when OpenAI client is not available."""
        result = _call_openai("Test prompt")
        assert result is None


class TestSummarization:
    """Test text summarization."""

    @patch('app.services.ai._call_openai')
    def test_summarize_with_openai(self, mock_openai):
        """Test summarization using OpenAI."""
        mock_openai.return_value = "• Key point 1\n• Key point 2\n• Key point 3"

        text = "This is a long text about various topics that needs to be summarized."
        result = summarize(text)

        assert "Key point" in result
        mock_openai.assert_called_once()

    @patch('app.services.ai._call_openai')
    @patch('app.services.ai.extract_keyphrases')
    def test_summarize_fallback(self, mock_keyphrases, mock_openai):
        """Test summarization fallback when OpenAI fails."""
        mock_openai.return_value = None  # OpenAI fails
        mock_keyphrases.return_value = ["machine learning", "data science", "artificial intelligence"]

        text = "This video discusses machine learning and data science with artificial intelligence applications."
        result = summarize(text)

        # Should use fallback logic
        assert "discusses" in result.lower()
        assert any(phrase in result.lower() for phrase in ["machine learning", "data science"])

    def test_summarize_empty_text(self):
        """Test summarization with empty text."""
        result = summarize("")
        assert isinstance(result, str)
        # Empty text should return empty string or minimal fallback
        assert len(result) >= 0


class TestChapterGeneration:
    """Test chapter generation."""

    @patch('app.services.ai._call_openai')
    def test_chapters_with_openai(self, mock_openai):
        """Test chapter generation using OpenAI."""
        mock_openai.return_value = "Introduction|0.0\nMain Content|120.5\nConclusion|240.0"

        text = "Video transcript content"
        result = chapters(text, duration=300.0)

        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == ("Introduction", 0.0)
        assert result[1] == ("Main Content", 120.5)
        assert result[2] == ("Conclusion", 240.0)

    @patch('app.services.ai._call_openai')
    @patch('app.services.ai.extract_keyphrases')
    def test_chapters_fallback(self, mock_keyphrases, mock_openai):
        """Test chapter generation fallback."""
        mock_openai.return_value = None
        mock_keyphrases.return_value = ["intro", "content", "conclusion"]

        text = "Video transcript"
        result = chapters(text, duration=240.0)

        assert isinstance(result, list)
        assert len(result) > 0
        # Should create evenly spaced chapters
        assert all(isinstance(title, str) and isinstance(start, (int, float)) for title, start in result)

    def test_chapters_no_duration(self):
        """Test chapter generation without duration."""
        with patch('app.services.ai._call_openai') as mock_openai:
            mock_openai.return_value = None

            text = "Video transcript"
            result = chapters(text, duration=None)

            assert isinstance(result, list)
            assert len(result) > 0


class TestTakeaways:
    """Test takeaway generation."""

    @patch('app.services.ai._call_openai')
    def test_takeaways_with_openai(self, mock_openai):
        """Test takeaway generation using OpenAI."""
        mock_openai.return_value = "1. First takeaway\n2. Second takeaway\n3. Third takeaway"

        text = "Educational content"
        result = takeaways(text)

        assert isinstance(result, list)
        assert len(result) == 3
        assert "First takeaway" in result
        assert "Second takeaway" in result
        assert "Third takeaway" in result

    @patch('app.services.ai._call_openai')
    @patch('app.services.ai.extract_keyphrases')
    def test_takeaways_fallback(self, mock_keyphrases, mock_openai):
        """Test takeaway generation fallback."""
        mock_openai.return_value = None
        mock_keyphrases.return_value = ["machine learning", "data analysis", "deep learning"]

        text = "Educational content"
        result = takeaways(text)

        assert isinstance(result, list)
        assert len(result) > 0
        # Should capitalize keyphrases
        assert all(phrase[0].isupper() for phrase in result)


class TestQuestionAnswering:
    """Test question answering."""

    @patch('app.services.ai._call_openai')
    def test_answer_with_openai(self, mock_openai):
        """Test question answering using OpenAI."""
        mock_openai.return_value = "Machine learning is a subset of artificial intelligence."

        text = "This video explains machine learning concepts and artificial intelligence."
        question = "What is machine learning?"
        result = answer(text, question)

        assert "machine learning" in result.lower()
        mock_openai.assert_called_once()

    @patch('app.services.ai._call_openai')
    def test_answer_fallback(self, mock_openai):
        """Test question answering fallback."""
        mock_openai.return_value = None

        text = "Machine learning is a powerful technique. It uses algorithms to learn from data."
        question = "What is machine learning?"
        result = answer(text, question)

        # Should find relevant sentence
        assert "machine learning" in result.lower()
        assert "powerful technique" in result or "algorithms" in result

    @patch('app.services.ai._call_openai')
    def test_answer_no_match(self, mock_openai):
        """Test question answering when no match found."""
        mock_openai.return_value = None

        text = "This video is about cooking recipes."
        question = "What is machine learning?"
        result = answer(text, question)

        # Should either return "don't know" or the best available sentence
        assert "don't know" in result.lower() or "cooking" in result.lower()


class TestEntityExtraction:
    """Test entity extraction."""

    @patch('app.services.ai._call_openai')
    def test_entities_with_openai(self, mock_openai):
        """Test entity extraction using OpenAI."""
        mock_openai.return_value = "1. Google\n2. Microsoft\n3. OpenAI\n4. PyTorch"

        text = "Google and Microsoft are competing with OpenAI in AI development using PyTorch."
        result = entities(text)

        assert isinstance(result, list)
        assert "Google" in result
        assert "Microsoft" in result
        assert "OpenAI" in result
        assert "PyTorch" in result

    @patch('app.services.ai._call_openai')
    def test_entities_fallback(self, mock_openai):
        """Test entity extraction fallback."""
        mock_openai.return_value = None

        text = "Apple Inc. and Google LLC are technology companies. Steve Jobs founded Apple."
        result = entities(text)

        assert isinstance(result, list)
        # Should find proper nouns
        assert any("Apple" in entity for entity in result)
        assert any("Google" in entity for entity in result)

    @patch('app.services.ai._call_openai')
    def test_entities_deduplication(self, mock_openai):
        """Test entity deduplication."""
        mock_openai.return_value = "Google\nGoogle Inc\ngoogle\nMicrosoft"

        text = "Google Google Inc and Microsoft"
        result = entities(text)

        # Should deduplicate case-insensitive
        google_entities = [e for e in result if "google" in e.lower()]
        assert len(google_entities) <= 2  # Should be deduplicated
