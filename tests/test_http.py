import json
from pathlib import Path

import requests

from crawlers.gem import GemAdapter, parse_gem_json
from crawlers.http import HttpResponse, HttpStatusError, PoliteClient, RobotsDisallowed
from crawlers.types import CrawlContext


class ScriptedSession:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.headers = {}

    def get(self, url, timeout=None, **kwargs):
        return self.request("GET", url, timeout=timeout, **kwargs)

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append((method, url))
        result = self.handler(method, url, kwargs)
        if isinstance(result, Exception):
            raise result
        return result


def _response(status, text, url):
    response = requests.Response()
    response.status_code = status
    response._content = text.encode()
    response.url = url
    response.headers["Content-Type"] = "text/html"
    response.encoding = "utf-8"
    return response


def test_retries_then_returns_the_successful_response():
    attempts = {"n": 0}
    sleeps = []

    def handler(method, url, kwargs):
        if url.endswith("/robots.txt"):
            return _response(404, "missing", url)
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise requests.ConnectionError("reset")
        return _response(200, "ok", url)

    client = PoliteClient(
        delay=0,
        max_attempts=3,
        session=ScriptedSession(handler),
        sleep=sleeps.append,
        rng=lambda: 0,
    )
    response = client.get("https://example.gov.in/tenders")
    assert isinstance(response, HttpResponse)
    assert response.text == "ok"
    assert attempts["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_robots_disallow_does_not_fetch_the_page():
    def handler(method, url, kwargs):
        if url.endswith("/robots.txt"):
            body = "User-agent: *\nDisallow: /private\n"
            return _response(200, body, url)
        return _response(200, "should-not-load", url)

    session = ScriptedSession(handler)
    client = PoliteClient(delay=0, session=session, sleep=lambda _s: None, rng=lambda: 0)
    try:
        client.get("https://example.gov.in/private/tenders")
        raised = False
    except RobotsDisallowed:
        raised = True
    assert raised
    assert not any(url.endswith("/private/tenders") for _method, url in session.calls)


def test_status_500_is_raised_after_retries():
    def handler(method, url, kwargs):
        if url.endswith("/robots.txt"):
            return _response(404, "", url)
        return _response(500, "down", url)

    client = PoliteClient(
        delay=0,
        max_attempts=2,
        session=ScriptedSession(handler),
        sleep=lambda _s: None,
        rng=lambda: 0,
    )
    try:
        client.get("https://example.gov.in/tenders")
        raised = False
    except HttpStatusError as exc:
        raised = True
        assert exc.status == 500
    assert raised


class MapClient:
    def __init__(self, pages):
        self.pages = pages
        self.posts = []
        self.gets = []
        self.requests_made = 0

    def post(self, url, **kwargs):
        self.posts.append(kwargs.get("data"))
        self.requests_made += 1
        page = json_page(kwargs.get("data"))
        return HttpResponse(200, self.pages[page], url)

    def get(self, url, **kwargs):
        self.gets.append(url)
        self.requests_made += 1
        if "bidplus.gem.gov.in" in url:
            raise requests.ConnectionError("tls reset")
        return HttpResponse(200, "<html>no rows</html>", url)


def json_page(data):
    payload = json.loads(data["payload"])
    return payload["page"]


def test_gem_json_retries_a_rejected_body_then_parses():
    page = (Path_fixtures() / "gem_global_page1.json").read_text()

    class RejectOnce:
        def __init__(self):
            self.posts = 0
            self.gets = []
            self.requests_made = 0

        def post(self, url, **kwargs):
            self.posts += 1
            self.requests_made += 1
            if self.posts == 1:
                return HttpResponse(200, "<html>Request Rejected</html>", url)
            return HttpResponse(200, page, url)

        def get(self, url, **kwargs):
            self.gets.append(url)
            self.requests_made += 1
            if "bidplus.gem.gov.in" in url:
                raise requests.ConnectionError("tls reset")
            return HttpResponse(200, "<html></html>", url)

    client = RejectOnce()
    result = GemAdapter(client).fetch(CrawlContext(marker={}, max_pages=1))
    assert client.posts == 2
    assert any(row.source_key == "GEM/2026/B/8071078" for row in result.records)
    assert not any("rejected" in error.lower() for error in result.errors)


def test_gem_incremental_cursor_stops_on_a_known_page():
    page = (Path_fixtures() / "gem_global_page1.json").read_text()
    client = MapClient({1: page, 2: page})
    adapter = GemAdapter(client)
    keys = [row.source_key for row in parse_gem_json(json.loads(page))[0]]
    result = adapter.fetch(
        CrawlContext(marker={"feeds": {"gem_json": {"recent_keys": keys}}}, max_pages=3, full=False)
    )
    assert len(client.posts) == 1
    assert result.records
    assert any("bidplus.gem.gov.in" in error for error in result.errors)


def Path_fixtures():
    return Path(__file__).resolve().parent / "fixtures"
