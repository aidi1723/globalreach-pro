from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import settings


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max(1, int(max_requests))
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        current = now if now is not None else time.time()
        with self._lock:
            events = self._events[key]
            cutoff = current - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_requests:
                retry_after = max(1, int(events[0] + self.window_seconds - current))
                return False, retry_after
            events.append(current)
            return True, 0


public_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.public_rate_limit_max_requests,
    window_seconds=settings.public_rate_limit_window_seconds,
)


def extract_client_ip(request: Request) -> str:
    if request.client and request.client.host:
        client_ip = request.client.host
        if settings.trust_proxy_headers and client_ip in settings.trusted_proxy_ips:
            forwarded_for = request.headers.get("x-forwarded-for", "").strip()
            if forwarded_for:
                forwarded_ip = forwarded_for.split(",")[0].strip()
                if forwarded_ip:
                    return forwarded_ip
        return client_ip
    return "unknown"


def enforce_public_rate_limit(request: Request):
    client_ip = extract_client_ip(request)
    key = f"{request.url.path}:{client_ip}"
    allowed, retry_after = public_rate_limiter.allow(key)
    if allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"请求过于频繁，请在 {retry_after} 秒后重试。",
        headers={"Retry-After": str(retry_after)},
    )
