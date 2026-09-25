from __future__ import annotations

import random
from dataclasses import dataclass, field
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

DEFAULT_USER_AGENT = (
    "TenderLens/0.1 (+https://github.com/tomlin7/tenderlens; public procurement research)"
)
RETRY_STATUSES = {429, 500, 502, 503, 504}


class RobotsDisallowed(Exception):
    def __init__(self, url: str):
        super().__init__(f"robots.txt disallows {url}")
        self.url = url


class HttpStatusError(Exception):
    def __init__(self, status: int, url: str, snippet: str):
        self.status = status
        self.url = url
        self.snippet = snippet
        super().__init__(f"HTTP {status} for {url}: {snippet[:160]}")


@dataclass
class HttpResponse:
    status_code: int
    text: str
    url: str
    headers: dict = field(default_factory=dict)

    def json(self):
        import json

        return json.loads(self.text)

    @classmethod
    def from_requests(cls, response: requests.Response) -> HttpResponse:
        return cls(
            status_code=response.status_code,
            text=response.text,
            url=response.url,
            headers={k.lower(): v for k, v in response.headers.items()},
        )


class PoliteClient:
    """GET/POST with per-host delay, robots.txt, and exponential backoff.

    ``sleep`` and ``now`` are injectable so tests do not wait on the clock.
    """

    def __init__(
        self,
        *,
        delay: float = 2.0,
        timeout: float = 30.0,
        max_attempts: int = 3,
        user_agent: str = DEFAULT_USER_AGENT,
        session: requests.Session | None = None,
        sleep=None,
        now=None,
        rng=None,
    ):
        import time

        self.delay = delay
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", user_agent)
        self.session.headers.setdefault("Accept-Language", "en")
        self.sleep = sleep or time.sleep
        self.now = now or time.monotonic
        self.rng = rng or random.random
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self.requests_made = 0

    def get(self, url: str, *, attempts: int | None = None, timeout: float | None = None, **kwargs):
        return self.request("GET", url, attempts=attempts, timeout=timeout, **kwargs)

    def post(
        self, url: str, *, attempts: int | None = None, timeout: float | None = None, **kwargs
    ):
        return self.request("POST", url, attempts=attempts, timeout=timeout, **kwargs)

    def request(
        self,
        method: str,
        url: str,
        *,
        attempts: int | None = None,
        timeout: float | None = None,
        **kwargs,
    ) -> HttpResponse:
        self._ensure_robots(url)
        if not self._allowed(url):
            raise RobotsDisallowed(url)
        tries = attempts or self.max_attempts
        last_error: Exception | None = None
        for attempt in range(tries):
            self._wait(url)
            try:
                response = self.session.request(
                    method, url, timeout=timeout or self.timeout, **kwargs
                )
                self.requests_made += 1
            except requests.RequestException as exc:
                self.requests_made += 1
                last_error = exc
                self._backoff(attempt, tries)
                continue
            if response.status_code in RETRY_STATUSES and attempt + 1 < tries:
                last_error = HttpStatusError(response.status_code, url, response.text[:200])
                self._backoff(attempt, tries)
                continue
            if response.status_code >= 400:
                raise HttpStatusError(
                    response.status_code, response.url or url, response.text[:200]
                )
            return HttpResponse.from_requests(response)
        if last_error:
            raise last_error
        raise HttpStatusError(0, url, "no response")

    def _ensure_robots(self, url: str) -> None:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base in self._robots:
            return
        robots_url = base + "/robots.txt"
        parser = RobotFileParser()
        self._wait(robots_url)
        try:
            response = self.session.get(robots_url, timeout=min(self.timeout, 20))
            self.requests_made += 1
            if response.status_code == 200 and response.text.strip():
                parser.parse(response.text.splitlines())
                parser.set_url(robots_url)
                self._robots[base] = parser
            else:
                # A missing robots.txt does not grant extra privilege; it also
                # does not forbid the public pages. Record it as "no rules".
                self._robots[base] = None
        except requests.RequestException:
            self.requests_made += 1
            self._robots[base] = None

    def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._robots.get(base)
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    def _wait(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        last = self._last.get(host)
        now = self.now()
        if last is not None:
            remain = self.delay - (now - last)
            if remain > 0:
                self.sleep(remain)
                now = self.now()
        self._last[host] = now

    def _backoff(self, attempt: int, tries: int) -> None:
        if attempt + 1 >= tries:
            return
        # 1s, 2s, 4s... plus up to 250ms of jitter.
        delay = (2**attempt) + (self.rng() * 0.25)
        self.sleep(delay)
