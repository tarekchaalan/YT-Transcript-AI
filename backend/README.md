# yt-ai backend

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Env (optional)
- OPENAI_API_KEY
- OPENAI_MODEL (default gpt-4o-mini)
- WHISPER_CPP_BIN (default whisper)
- WHISPER_CPP_MODEL (default ggml-base.en.bin)
