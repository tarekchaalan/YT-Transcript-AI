# yt-ai

Full-stack YouTube AI assistant with drop-in URLs, transcript pipeline, AI tools, and exports.

## Features
- Drop-in URL: replace `youtube.com/...` with this domain → lands on `/v/[id]`
- Smart ID parsing: supports watch, shorts, youtu.be, embed, live
- Transcript pipeline: YouTubeTranscriptAPI → fallback to yt-dlp + whisper.cpp
- Cleanup: DeepMultilingualPunctuation for punctuation/cases
- AI tools: TL;DR, chapters, takeaways, Q&A, entity highlights (OpenAI optional)
- Exports: copy, .txt, .srt, .vtt, chapter JSON
- Player linking: timestamps jump to original YouTube time
- Limits: per-IP rate limiting and daily quotas
- UX: dark mode, keyboard shortcuts (j/k), sticky mini-TOC, shareable URLs

## Prerequisites
- macOS with Homebrew
- Python 3.12+
- Node 18+
- ffmpeg (for audio extraction)
- whisper.cpp binary and model (optional, for fallback)

Install ffmpeg:
```bash
brew install ffmpeg
```

Install whisper.cpp (optional):
```bash
brew install whisper-cpp
# or download a binary and set WHISPER_CPP_BIN
# Model example:
wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin -O ggml-base.en.bin
```

## Backend
Create and activate virtualenv, install deps:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Environment (optional):
```bash
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o-mini
export WHISPER_CPP_BIN=whisper
export WHISPER_CPP_MODEL=ggml-base.en.bin
```

Run:
```bash
uvicorn app.main:app --reload --port 8000
```

## Frontend
```bash
cd frontend
npm install
# Configure backend URL for local dev
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

Visit:
- Home: http://localhost:3000
- Drop-in: paste `https://www.youtube.com/watch?v=VIDEOID` into the top bar, or open `http://localhost:3000/v/VIDEOID`

## Testing

Run all tests:
```bash
./run-tests.sh
```

Backend tests only:
```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

Frontend tests only:
```bash
cd frontend
npm test
```

Test coverage includes:
- **Models & Schemas**: Data validation, serialization
- **Transcript Pipeline**: YouTube API, whisper fallback, punctuation
- **AI Services**: OpenAI integration, keyword extraction, fallbacks
- **API Endpoints**: All routes, error handling, rate limiting
- **Frontend Components**: Video page, keyboard shortcuts, UI interactions
- **Rate Limiting**: Per-IP quotas, abuse protection

## Notes
- The punctuation step downloads a small transformer at first run; it may take time.
- The whisper.cpp fallback requires ffmpeg and a whisper model; if unavailable, the app will skip fallback.
- Rate limits are in-memory and per-process; for production use an external store.
