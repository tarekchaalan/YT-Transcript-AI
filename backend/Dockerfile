# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install system deps (ffmpeg for exports/yt-dlp)
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
  && pip install --no-cache-dir yt-dlp

# Copy backend source
COPY app ./app

ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1 \
    UVICORN_WORKERS=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


