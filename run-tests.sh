#!/bin/bash

# Test runner for yt-ai project
set -e

echo "🧪 Running yt-ai test suite..."
echo "================================"

# Backend tests
echo ""
echo "📦 Backend Tests"
echo "----------------"
cd backend
source .venv/bin/activate

echo "Running unit tests..."
python -m pytest tests/ -v --tb=short

echo "Running specific test categories..."
echo "  • Models and schemas..."
python -m pytest tests/test_models.py -q

echo "  • YouTube ID extraction..."
python -m pytest tests/test_transcript.py::TestYouTubeIDExtraction -q

echo "  • AI service (with mocks)..."
python -m pytest tests/test_ai.py::TestKeyphraseExtraction -q

echo "  • Rate limiting..."
python -m pytest tests/test_limits.py::TestInMemoryRateLimiter -q

# Frontend tests
echo ""
echo "🎨 Frontend Tests"
echo "-----------------"
cd ../frontend

echo "Running component tests..."
npm test -- --watchAll=false --verbose=false --passWithNoTests

echo ""
echo "✅ All tests completed!"
echo ""
echo "📊 Test Coverage Summary:"
echo "  • Backend: Models, AI services, transcript parsing, rate limiting"
echo "  • Frontend: Components, keyboard shortcuts, video page"
echo "  • API: Endpoints, error handling, data validation"
echo ""
echo "🚀 Ready for deployment!"
