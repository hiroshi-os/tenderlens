from __future__ import annotations

import time

from django.conf import settings
from django.utils import timezone

from crawlers.http import PoliteClient
from crawlers.registry import SOURCES, build_adapters
from crawlers.types import CrawlContext
from etl.load import ingest
from tenders.models import CrawlCursor, CrawlRun


def run_all(
    sources: list[str] | None = None,
    *,
    max_pages: int | None = None,
    max_orgs: int | None = None,
    max_details: int | None = None,
    delay: float | None = None,
    full: bool = False,
    client=None,
) -> dict:
    selected = list(sources or SOURCES)
    unknown = [name for name in selected if name not in SOURCES]
    if unknown:
        raise ValueError(f"Unknown sources: {', '.join(unknown)}")
    http = client or PoliteClient(
        delay=delay if delay is not None else settings.CRAWL_DELAY_SECONDS
    )
    adapters = build_adapters(http)
    summary = {}
    for name in selected:
        summary[name] = run_source(
            adapters[name],
            max_pages=max_pages if max_pages is not None else settings.CRAWL_MAX_PAGES,
            max_orgs=max_orgs if max_orgs is not None else settings.CRAWL_MAX_ORGS,
            max_details=max_details if max_details is not None else settings.CRAWL_MAX_DETAILS,
            full=full,
        )
    summary["http_requests"] = http.requests_made
    return summary


def run_source(adapter, *, max_pages: int, max_orgs: int, max_details: int, full: bool) -> dict:
    cursor, _created = CrawlCursor.objects.get_or_create(
        source=adapter.source, defaults={"marker": {}}
    )
    run = CrawlRun.objects.create(
        source=adapter.source, marker_before=cursor.marker or {}, status=CrawlRun.Status.RUNNING
    )
    started = time.perf_counter()
    try:
        ctx = CrawlContext(
            marker=cursor.marker or {},
            max_pages=max_pages,
            max_orgs=max_orgs,
            max_details=max_details,
            full=full,
        )
        fetched = adapter.fetch(ctx)
        fetch_seconds = time.perf_counter() - started
        load_started = time.perf_counter()
        stats = ingest(fetched.records, fetched.awards)
        load_seconds = time.perf_counter() - load_started
        loaded = stats.created + stats.updated + stats.unchanged
        cursor.marker = fetched.marker
        cursor.save(update_fields=["marker", "updated_at"])
        payload = {
            "fetched": len(fetched.records),
            "created": stats.created,
            "updated": stats.updated,
            "unchanged": stats.unchanged,
            "awards_created": stats.awards_created,
            "awards_updated": stats.awards_updated,
            "errors": fetched.errors,
            "portal_reported_totals": fetched.portal_reported_totals,
            "fetch_seconds": round(fetch_seconds, 3),
            "ingest_seconds": round(load_seconds, 3),
            "ingest_rows_per_second": round(loaded / load_seconds, 3) if load_seconds else None,
        }
        run.status = CrawlRun.Status.SUCCESS
        run.marker_after = fetched.marker
        run.stats = payload
        run.error = "\n".join(fetched.errors)[:4000]
        run.finished_at = timezone.now()
        run.save()
        return payload
    except Exception as exc:
        run.status = CrawlRun.Status.FAILED
        run.error = str(exc)[:4000]
        run.finished_at = timezone.now()
        run.save()
        return {"error": str(exc), "status": "failed"}
