from __future__ import annotations

import time
from typing import Dict, Tuple

from fastapi import Request, HTTPException


class InMemoryRateLimiter:
    """Simple per-IP sliding window rate limiter and quota.

    Not for multi-instance production, but good enough to guard abuse.
    """

    def __init__(self, max_requests_per_minute: int = 30, daily_quota: int = 200):
        self.max_requests_per_minute = max_requests_per_minute
        self.daily_quota = daily_quota
        self.minute_buckets: Dict[str, Tuple[int, float]] = {}
        self.daily_counts: Dict[str, Tuple[int, int]] = {}

    def check(self, ip: str) -> None:
        now = time.time()
        # minute window
        count, ts = self.minute_buckets.get(ip, (0, now))
        if now - ts >= 60:
            count = 0
            ts = now
        count += 1
        self.minute_buckets[ip] = (count, ts)
        if count > self.max_requests_per_minute:
            raise HTTPException(status_code=429, detail="Too many requests")

        # daily quota
        day = int(now // 86400)
        dcount, dday = self.daily_counts.get(ip, (0, day))
        if dday != day:
            dcount = 0
            dday = day
        dcount += 1
        self.daily_counts[ip] = (dcount, dday)
        if dcount > self.daily_quota:
            raise HTTPException(status_code=429, detail="Daily quota exceeded")


limiter = InMemoryRateLimiter(max_requests_per_minute=20, daily_quota=150)


async def guard_request(request: Request) -> None:
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    limiter.check(client_ip)


