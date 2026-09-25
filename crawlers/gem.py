"""Government e-Marketplace bids.

Two public surfaces are used.

1. ``https://bidplus-global.gem.gov.in/all-bids-data`` is the JSON document the
   public global-tender page already posts to (``ci_csrf_token`` is empty on
   that page; no login). It returns bid number, title, ministry, department,
   and start/end timestamps. It does not include the contract value or the
   awardee. As of 2026-09-25 this feed listed global tenders only (numFound 21
   for ongoing bids).

2. Domestic GeM bids are republished as HTML by CPPP at
   ``/cppp/gemtender``. ``bidplus.gem.gov.in`` and ``gem.gov.in`` reset the TLS
   handshake from this network, so the direct domestic portal is probed once
   and skipped when it fails. The CPPP mirror is the same public bid list
   (bid numbers of the form ``GEM/YYYY/B/N``).

Unknown GeM status filters are not used: several non-existent
``bidStatusType`` values silently returned a different result set, so awards
are not inferred from them.
"""

from __future__ import annotations

import json

from crawlers.http import HttpStatusError, RobotsDisallowed
from crawlers.parseutil import (
    GEM_BID_RE,
    absolute,
    cell_text,
    data_rows,
    first_match,
    first_value,
    ministry_from_text,
    next_numbered_page,
    parse_iso_datetime,
    parse_portal_datetime,
    scrub_mapping,
)
from crawlers.types import CrawlContext, FetchResult, RawTender

GEM_JSON_URL = "https://bidplus-global.gem.gov.in/all-bids-data"
GEM_HOME = "https://bidplus-global.gem.gov.in/"
GEM_DOMESTIC = "https://bidplus.gem.gov.in/all-bids"
CPPP_GEM_URL = "https://eprocure.gov.in/cppp/gemtender"
PLACEHOLDER_CATEGORY = "globaltendercategory"


def parse_gem_json(payload: dict) -> tuple[list[RawTender], int | None]:
    response = (payload.get("response") or {}).get("response") or {}
    docs = response.get("docs") or []
    total = response.get("numFound")
    records: list[RawTender] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        doc = scrub_mapping(doc)
        bid = first_value(doc.get("b_bid_number")) or ""
        bid = bid.replace("\\/", "/")
        source_key = first_match(GEM_BID_RE, bid) or bid
        if not source_key:
            continue
        title = first_value(doc.get("bbt_title")) or source_key
        category_values = doc.get("b_category_name") or []
        category = ""
        if category_values:
            raw_category = str(first_value(category_values) or "")
            if raw_category.lower() != PLACEHOLDER_CATEGORY:
                category = raw_category
        ministry = first_value(doc.get("ba_official_details_minName")) or ""
        department = first_value(doc.get("ba_official_details_deptName")) or ""
        bid_id = first_value(doc.get("b_id"))
        quarter = first_value(doc.get("qtr_dir")) or ""
        upload = first_value(doc.get("b_is_new_upload"))
        detail = ""
        if bid_id:
            detail = (
                f"https://bidplus-global.gem.gov.in/showbidDocument/{bid_id}/{quarter}/{upload}"
            )
        quantity = first_value(doc.get("b_total_quantity"))
        high = first_value(doc.get("is_high_value"))
        records.append(
            RawTender(
                source="gem",
                source_key=source_key,
                feed="gem_json",
                title=str(title),
                description=str(title),
                organisation=str(department or ministry),
                department=str(department or ""),
                ministry=str(ministry or ministry_from_text(department)),
                category=category or "Global tender",
                quantity=int(quantity) if isinstance(quantity, int) else None,
                is_high_value=bool(high) if isinstance(high, bool) else None,
                published_at=parse_iso_datetime(first_value(doc.get("final_start_date_sort"))),
                deadline_at=parse_iso_datetime(first_value(doc.get("final_end_date_sort"))),
                detail_url=detail,
                status="active",
                raw={"b_id": bid_id, "is_high_value": high},
            )
        )
    return records, int(total) if isinstance(total, int) else None


def parse_gem_mirror_html(
    html: str, page_url: str = CPPP_GEM_URL
) -> tuple[list[RawTender], int | None]:
    _soup, rows = data_rows(html)
    records: list[RawTender] = []
    for cells in rows:
        if len(cells) < 6:
            continue
        blob = cell_text(cells[3])
        source_key = first_match(GEM_BID_RE, blob)
        if not source_key:
            continue
        anchor = cells[3].find("a")
        quantity = None
        tail = blob.split(source_key, 1)[-1].strip(" /")
        if tail.isdigit():
            quantity = int(tail)
        category = cell_text(cells[4])
        organisation = cell_text(cells[5])
        department = cell_text(cells[6]) if len(cells) > 6 else ""
        title = category[:240] if category else source_key
        records.append(
            RawTender(
                source="gem",
                source_key=source_key,
                feed="gem_cppp_mirror",
                title=title,
                description=category,
                organisation=organisation,
                department=department,
                ministry=ministry_from_text(organisation, department),
                category=category[:300],
                quantity=quantity,
                published_at=parse_portal_datetime(cell_text(cells[1])),
                deadline_at=parse_portal_datetime(cell_text(cells[2])),
                detail_url=absolute(page_url, anchor.get("href") if anchor else ""),
                status="active",
                raw={},
            )
        )
    return records, _total_bids(html)


def _total_bids(html: str) -> int | None:
    import re

    match = re.search(r"Total Bid\(s\)\s*:?\s*([0-9,]+)", html, re.I)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


class GemAdapter:
    source = "gem"

    def __init__(self, client):
        self.client = client

    def fetch(self, ctx: CrawlContext) -> FetchResult:
        errors: list[str] = []
        records: list[RawTender] = []
        totals: dict = {}
        marker = dict(ctx.marker or {})
        feeds = dict(marker.get("feeds") or {})

        errors.extend(self._probe_domestic())
        json_rows, json_total, json_keys, json_errors = self._json_pages(
            recent_keys=set((feeds.get("gem_json") or {}).get("recent_keys") or []),
            max_pages=ctx.max_pages,
            full=ctx.full,
        )
        records.extend(json_rows)
        errors.extend(json_errors)
        if json_total is not None:
            totals["gem_json_ongoing"] = json_total
        if json_rows:
            feeds["gem_json"] = {"recent_keys": json_keys[:50]}

        mirror_rows, mirror_total, mirror_keys, mirror_errors = self._mirror_pages(
            recent_keys=set((feeds.get("gem_cppp_mirror") or {}).get("recent_keys") or []),
            max_pages=ctx.max_pages,
            full=ctx.full,
        )
        records.extend(mirror_rows)
        errors.extend(mirror_errors)
        if mirror_total is not None:
            totals["gem_cppp_mirror"] = mirror_total
        if mirror_rows:
            feeds["gem_cppp_mirror"] = {"recent_keys": mirror_keys[:50]}

        marker["feeds"] = feeds
        return FetchResult(
            records=records,
            awards=[],
            errors=errors,
            http_requests=self.client.requests_made,
            marker=marker,
            portal_reported_totals=totals,
        )

    def _probe_domestic(self) -> list[str]:
        try:
            self.client.get(GEM_DOMESTIC, attempts=1, timeout=12)
        except Exception as exc:
            return [
                "bidplus.gem.gov.in did not accept a connection from this network "
                f"({type(exc).__name__}: {exc}). Domestic bids are taken from the "
                "public CPPP GeM mirror instead. No captcha or login bypass is attempted."
            ]
        return []

    def _json_pages(self, *, recent_keys, max_pages, full):
        collected: list[RawTender] = []
        errors: list[str] = []
        front_keys: list[str] = []
        total = None
        for page in range(1, max_pages + 1):
            payload, error = self._post_bids(page)
            if error:
                errors.append(error)
                break
            if payload.get("code") not in (200, "200", None) and not (
                payload.get("response") or {}
            ):
                errors.append(f"GeM all-bids-data returned code {payload.get('code')}.")
                break
            rows, reported = parse_gem_json(payload)
            if total is None:
                total = reported
            if not rows:
                break
            if page == 1:
                front_keys = [row.source_key for row in rows]
            known = sum(1 for row in rows if row.source_key in recent_keys)
            collected.extend(rows)
            if not full and (known == len(rows) or known):
                break
            if reported is not None and page * 10 >= reported:
                break
            if len(rows) < 10:
                break
        return collected, total, front_keys, errors

    def _post_bids(self, page: int):
        """POST the public bid search. The edge sometimes answers with an HTML rejection instead of JSON.

        The same request is retried. The user agent and headers stay the same; this is not a bypass.
        """
        body = {
            "payload": json.dumps(
                {
                    "page": page,
                    "param": {"searchBid": "", "searchType": "fullText"},
                    "filter": {
                        "bidStatusType": "ongoing_bids",
                        "byType": "all",
                        "highBidValue": "",
                        "byEndDate": {"from": "", "to": ""},
                        "sort": "Bid-Start-Date-Latest",
                    },
                }
            ),
            "ci_csrf_token": "",
        }
        headers = {
            "Referer": GEM_HOME,
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        last_error = "GeM all-bids-data did not return JSON."
        for attempt in range(3):
            try:
                response = self.client.post(GEM_JSON_URL, data=body, headers=headers)
            except (HttpStatusError, RobotsDisallowed) as exc:
                return None, str(exc)
            text = response.text.lstrip()
            if text.startswith("{") or text.startswith("["):
                try:
                    return json.loads(text), None
                except ValueError:
                    last_error = "GeM all-bids-data body was not valid JSON."
            elif "Request Rejected" in response.text:
                last_error = (
                    "GeM all-bids-data rejected the request with an HTML block page. "
                    "The same POST was retried without changing headers."
                )
            else:
                last_error = "GeM all-bids-data returned a non-JSON document."
            if attempt == 2:
                break
        return None, last_error

    def _mirror_pages(self, *, recent_keys, max_pages, full):
        collected: list[RawTender] = []
        errors: list[str] = []
        front_keys: list[str] = []
        total = None
        url = CPPP_GEM_URL
        page = 1
        while url and page <= max_pages:
            try:
                response = self.client.get(url)
            except (HttpStatusError, RobotsDisallowed) as exc:
                errors.append(str(exc))
                break
            rows, reported = parse_gem_mirror_html(response.text, response.url)
            if total is None:
                total = reported
            if not rows:
                errors.append(f"CPPP GeM mirror page {page} contained no bid rows.")
                break
            if page == 1:
                front_keys = [row.source_key for row in rows]
            known = sum(1 for row in rows if row.source_key in recent_keys)
            collected.extend(rows)
            if not full and (known == len(rows) or known):
                break
            nxt = next_numbered_page(response.text, response.url, page)
            if not nxt:
                break
            url = nxt
            page += 1
        return collected, total, front_keys, errors
