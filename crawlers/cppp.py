"""Central Public Procurement Portal (eprocure.gov.in/cppp).

CPPP publishes server-rendered HTML tables. There is no documented public JSON
API. Two listings responded from this network on 2026-09-25:

* ``/cppp/globaltenders`` — central global tenders (page 1 is the HTML landing
  page; later pages use the site's own base64 ``url=`` links).
* ``/cppp/gemtender`` — GeM bids mirrored by CPPP. Parsed by the GeM adapter.

``/cppp/latestactivetendersnew`` and ``/cppp/resultoftendersnew`` returned HTTP
500 from this network. They are still requested, and a persistent 500 is
recorded rather than papered over. Detail pages (``tendersfullview``) also
returned 500, so estimated value and EMD are left empty for this source.
The on-page search form is captcha-gated and is not submitted.
"""

from __future__ import annotations

from crawlers.http import HttpStatusError, RobotsDisallowed
from crawlers.parseutil import (
    TENDER_ID_RE,
    absolute,
    cell_text,
    data_rows,
    first_match,
    ministry_from_text,
    next_numbered_page,
    parse_portal_datetime,
    reported_total,
)
from crawlers.types import CrawlContext, FetchResult, RawTender

CPPP_HOME = "https://eprocure.gov.in/cppp/"
GLOBAL_URL = "https://eprocure.gov.in/cppp/globaltenders"
ACTIVE_URL = "https://eprocure.gov.in/cppp/latestactivetendersnew"
AWARDS_URL = "https://eprocure.gov.in/cppp/resultoftendersnew"


def parse_cppp_global_html(
    html: str, page_url: str = GLOBAL_URL
) -> tuple[list[RawTender], int | None]:
    _soup, rows = data_rows(html)
    records: list[RawTender] = []
    for cells in rows:
        if len(cells) < 6:
            continue
        blob = cell_text(cells[4])
        source_key = first_match(TENDER_ID_RE, blob)
        if not source_key:
            continue
        anchor = cells[4].find("a")
        title = cell_text(anchor) if anchor else blob
        organisation = cell_text(cells[5])
        reference = blob
        if title and title in reference:
            reference = reference.replace(title, "", 1).strip(" /")
        reference = reference.replace(source_key, "").strip(" /")
        records.append(
            RawTender(
                source="cppp",
                source_key=source_key,
                feed="cppp_global",
                title=title or source_key,
                description=title,
                reference_number=reference,
                organisation=organisation,
                ministry=ministry_from_text(organisation),
                published_at=parse_portal_datetime(cell_text(cells[1])),
                deadline_at=parse_portal_datetime(cell_text(cells[2])),
                opening_at=parse_portal_datetime(cell_text(cells[3])),
                detail_url=absolute(page_url, anchor.get("href") if anchor else ""),
                status="active",
                raw={"corrigendum": cell_text(cells[6]) if len(cells) > 6 else ""},
            )
        )
    return records, reported_total(html, "Total Tenders")


class CpppAdapter:
    source = "cppp"

    def __init__(self, client):
        self.client = client

    def fetch(self, ctx: CrawlContext) -> FetchResult:
        errors: list[str] = []
        records: list[RawTender] = []
        totals: dict = {}
        marker = dict(ctx.marker or {})
        feeds = dict(marker.get("feeds") or {})

        global_rows, global_total, global_keys, global_errors = self._paged(
            GLOBAL_URL,
            parse_cppp_global_html,
            recent_keys=set((feeds.get("cppp_global") or {}).get("recent_keys") or []),
            max_pages=ctx.max_pages,
            full=ctx.full,
        )
        records.extend(global_rows)
        errors.extend(global_errors)
        if global_total is not None:
            totals["cppp_global"] = global_total
        if global_rows:
            feeds["cppp_global"] = {"recent_keys": global_keys[:50]}

        active_error = self._probe(ACTIVE_URL, "CPPP latest active tenders")
        if active_error:
            errors.append(active_error)
        award_error = self._probe(AWARDS_URL, "CPPP award of contract listing")
        if award_error:
            errors.append(award_error)

        marker["feeds"] = feeds
        return FetchResult(
            records=records,
            awards=[],
            errors=errors,
            http_requests=self.client.requests_made,
            marker=marker,
            portal_reported_totals=totals,
        )

    def _paged(self, start_url, parser, *, recent_keys, max_pages, full):
        collected: list[RawTender] = []
        errors: list[str] = []
        front_keys: list[str] = []
        total = None
        url = start_url
        page = 1
        while url and page <= max_pages:
            try:
                response = self.client.get(url)
            except (HttpStatusError, RobotsDisallowed) as exc:
                errors.append(str(exc))
                break
            rows, reported = parser(response.text, response.url)
            if total is None:
                total = reported
            if not rows:
                errors.append(f"CPPP page {page} at {url} contained no tender rows.")
                break
            if page == 1:
                front_keys = [row.source_key for row in rows]
            known = sum(1 for row in rows if row.source_key in recent_keys)
            collected.extend(rows)
            if not full and known == len(rows):
                break
            if not full and known:
                break
            nxt = next_numbered_page(response.text, response.url, page)
            if not nxt:
                break
            url = nxt
            page += 1
        return collected, total, front_keys, errors

    def _probe(self, url: str, label: str) -> str | None:
        try:
            response = self.client.get(url, attempts=2)
        except (HttpStatusError, RobotsDisallowed) as exc:
            return (
                f"{label} ({url}) could not be read ({exc}). No rows were invented for this feed."
            )
        if "unexpected error" in response.text.lower() or len(response.text) < 200:
            return f"{label} ({url}) returned an error page. No rows were collected."
        return None
