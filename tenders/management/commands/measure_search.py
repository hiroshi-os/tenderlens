"""Record EXPLAIN (ANALYZE) for the full-text query with and without the GIN index."""

import json
import os
import platform
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from tenders.models import Tender


class Command(BaseCommand):
    help = "Measure the main search query before and after the GIN index, then restore the index."

    def add_arguments(self, parser):
        parser.add_argument("--term", default="")
        parser.add_argument(
            "--output",
            default="docs/measurements/search.json",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise SystemExit("measure_search requires PostgreSQL")
        count = Tender.objects.count()
        if count == 0:
            raise SystemExit("No tenders loaded, so there is nothing to measure.")
        term = options["term"] or _term_from_data()
        sql = """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT id
            FROM tenders_tender
            WHERE search_vector @@ plainto_tsquery('english', %s)
        """
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE tenders_tender")
            with_index = _explain(cursor, sql, term)
            cursor.execute("SET enable_seqscan = off")
            try:
                forced = _explain(cursor, sql, term)
            finally:
                cursor.execute("SET enable_seqscan = on")
            cursor.execute("DROP INDEX IF EXISTS tender_search_gin")
            try:
                cursor.execute("ANALYZE tenders_tender")
                without_index = _explain(cursor, sql, term)
            finally:
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS tender_search_gin "
                    "ON tenders_tender USING GIN (search_vector)"
                )
                cursor.execute("ANALYZE tenders_tender")
        payload = {
            "measured_at": datetime.now(UTC).isoformat(),
            "term": term,
            "rows": count,
            "note": (
                "with_gin_index is the plan PostgreSQL chose while tender_search_gin existed. "
                "without_gin_index is the same SQL after that index was dropped. "
                "forced_index_scan disables sequential scans so the GIN index has to be used. "
                "All three ran against cached pages on this VM."
            ),
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "cpu_count": os.cpu_count(),
                "memory": _memory(),
                "postgres": _postgres_version(),
                "database": settings.DATABASES["default"]["NAME"],
            },
            "without_gin_index": without_index,
            "with_gin_index": with_index,
            "forced_index_scan": forced,
        }
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n")
        self.stdout.write(json.dumps(payload, indent=2))


def _explain(cursor, sql: str, term: str) -> dict:
    cursor.execute(sql, [term])
    plan = cursor.fetchone()[0][0]
    return {
        "planning_ms": plan.get("Planning Time"),
        "execution_ms": plan.get("Execution Time"),
        "node": (plan.get("Plan") or {}).get("Node Type"),
        "plan": plan,
    }


def _term_from_data() -> str:
    title = Tender.objects.exclude(title="").values_list("title", flat=True).first() or "tender"
    for token in title.replace("/", " ").split():
        letters = "".join(ch for ch in token if ch.isalpha())
        if len(letters) >= 5:
            return letters.lower()
    return "tender"


def _memory() -> str:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return ""
    return ""


def _postgres_version() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SHOW server_version")
        return cursor.fetchone()[0]
