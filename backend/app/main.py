from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app.api.routes import router as api_router
from app.core.limits import guard_request


app = FastAPI(title="yt-ai", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse, dependencies=[Depends(guard_request)])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


class ParseRequest(BaseModel):
    url: str


class ParseResponse(BaseModel):
    video_id: str


def extract_youtube_id(url: str) -> str:
    # Handles youtube.com/watch?v=, youtu.be/, shorts/, embed/
    import re

    patterns = [
        r"(?:v=|v%3D)([a-zA-Z0-9_-]{11})",  # watch URLs and encoded
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/live/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    # As a last resort, capture a 11-char token
    m = re.search(r"([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)
    raise ValueError("Could not parse YouTube video id")


@app.post("/parse", response_model=ParseResponse, dependencies=[Depends(guard_request)])
async def parse(req: ParseRequest) -> ParseResponse:
    try:
        vid = extract_youtube_id(req.url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
    return ParseResponse(video_id=vid)


app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


