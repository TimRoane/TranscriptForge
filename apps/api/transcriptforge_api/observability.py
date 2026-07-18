"""Low-cardinality API request metrics and correlation identifiers."""

from __future__ import annotations

import re
import threading
import time
from uuid import uuid4

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
logger = structlog.get_logger("transcriptforge.api")


class ApiMetrics:
    """Process-local metrics suitable for health checks and Prometheus scraping."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._requests = 0
        self._duration_seconds = 0.0
        self._status_classes: dict[str, int] = {}

    def start(self) -> None:
        with self._lock:
            self._active += 1

    def finish(self, status_code: int, duration_seconds: float) -> None:
        status_class = f"{status_code // 100}xx"
        with self._lock:
            self._active -= 1
            self._requests += 1
            self._duration_seconds += duration_seconds
            self._status_classes[status_class] = self._status_classes.get(status_class, 0) + 1

    def render(self) -> str:
        with self._lock:
            active = self._active
            requests = self._requests
            duration = self._duration_seconds
            status_classes = dict(self._status_classes)
        lines = [
            "# HELP transcriptforge_api_requests_total Completed HTTP requests.",
            "# TYPE transcriptforge_api_requests_total counter",
            f"transcriptforge_api_requests_total {requests}",
            "# HELP transcriptforge_api_request_duration_seconds_total Total request duration.",
            "# TYPE transcriptforge_api_request_duration_seconds_total counter",
            f"transcriptforge_api_request_duration_seconds_total {duration:.9f}",
            "# HELP transcriptforge_api_active_requests Currently executing HTTP requests.",
            "# TYPE transcriptforge_api_active_requests gauge",
            f"transcriptforge_api_active_requests {active}",
            "# HELP transcriptforge_api_responses_total Completed responses by status class.",
            "# TYPE transcriptforge_api_responses_total counter",
        ]
        lines.extend(
            f'transcriptforge_api_responses_total{{status_class="{status_class}"}} {count}'
            for status_class, count in sorted(status_classes.items())
        )
        return "\n".join(lines) + "\n"


api_metrics = ApiMetrics()


class RequestObservabilityMiddleware:
    """Attach a safe request ID, emit one completion event, and update metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex
        started = time.perf_counter()
        status_code = 500
        api_metrics.start()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration = time.perf_counter() - started
            api_metrics.finish(status_code, duration)
            logger.info(
                "http_request_complete",
                request_id=request_id,
                method=scope["method"],
                path=scope["path"],
                status_code=status_code,
                duration_ms=round(duration * 1000, 3),
            )
