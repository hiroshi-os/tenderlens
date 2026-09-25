"""Tamil Nadu GePNIC portal (tntenders.gov.in).

The public "Tenders by Organisation" index lists each buyer and a count, with
a session-scoped direct link. Following that link inside the same cookie jar
returns the buyer's active tenders without submitting the captcha on the
search form. Tender detail pages reached the same way publish EMD and tender
value. Advanced search and "Result of Tenders" are captcha forms; those forms
are not submitted.

Direct links go stale when the Tapestry session expires. A stale response is
detected and the index is loaded once more.

Maharashtra's portal (mahatenders.gov.in) publishes ``Disallow: /`` in
robots.txt and is not crawled. The same GePNIC search captcha is present on
the other state portals that were checked; Tamil Nadu is the state source
because its organisation index and detail pages are public.
"""

from __future__ import annotations

from crawlers.http import HttpStatusError, RobotsDisallowed
from crawlers.parseutil import (
    TENDER_ID_RE,
    absolute,
    cell_text,
    clean_text,
    data_rows,
    first_match,
    ministry_from_text,
    parse_inr,
    parse_portal_datetime,
)
from crawlers.types import CrawlContext, FetchResult, OrgRef, RawTender

TN_BASE = "https://tntenders.gov.in"
ORG_INDEX = TN_BASE + "/nicgep/app?page=FrontEndTendersByOrganisation&service=page"
RESULTS = TN_BASE + "/nicgep/app?page=ResultOfTenders&service=page"
STATE = "Tamil Nadu"


def parse_org_index(html: str, page_url: str = ORG_INDEX) -> list[OrgRef]:
    _soup, rows = data_rows(html)
    orgs: list[OrgRef] = []
    for cells in rows:
        if len(cells) < 3:
            continue
        name = cell_text(cells[1])
        link = cells[2].find("a")
        if not name or link is None:
            continue
        count_text = cell_text(link).replace(",", "")
        if not count_text.isdigit():
            continue
        orgs.append(
            OrgRef(name=name, count=int(count_text), url=absolute(page_url, link.get("href")))
        )
    return orgs


def parse_tn_tender_list(html: str, page_url: str) -> list[RawTender]:
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
        reference = cell_text(anchor).strip("[]") if anchor else ""
        chain = cell_text(cells[5])
        parts = [part.strip() for part in chain.split("||") if part.strip()]
        organisation = parts[0] if parts else chain
        department = " / ".join(parts[1:]) if len(parts) > 1 else ""
        records.append(
            RawTender(
                source="tntenders",
                source_key=source_key,
                feed="tntenders",
                title=reference or source_key,
                description="",
                reference_number=reference,
                organisation=organisation,
                department=department,
                ministry=ministry_from_text(chain),
                state=STATE,
                published_at=parse_portal_datetime(cell_text(cells[1])),
                deadline_at=parse_portal_datetime(cell_text(cells[2])),
                opening_at=parse_portal_datetime(cell_text(cells[3])),
                detail_url=absolute(page_url, anchor.get("href") if anchor else ""),
                status="active",
                raw={"organisation_chain": chain},
            )
        )
    return records


def apply_tn_detail(record: RawTender, html: str) -> RawTender:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}
    for caption in soup.select("td.td_caption"):
        value_cell = caption.find_next_sibling("td")
        if value_cell is None:
            continue
        fields[clean_text(caption.get_text(" ", strip=True))] = clean_text(
            value_cell.get_text(" ", strip=True)
        )
    description = _field(fields, "Work Description")
    title = _field(fields, "Title")
    if description:
        record.description = description
    if title and title != record.reference_number:
        record.title = title
    elif description:
        record.title = description
    category = _field(fields, "Tender Category")
    product = _field(fields, "Product Category")
    if category:
        record.category = category
    if product:
        record.raw["product_category"] = product
    record.emd_inr = parse_inr(_field_prefix(fields, "EMD Amount"))
    record.estimated_value_inr = parse_inr(_field_prefix(fields, "Tender Value"))
    location = _field(fields, "Location")
    pincode = _field(fields, "Pincode")
    if location:
        record.location = location
    if pincode:
        record.pincode = pincode
    chain = _field(fields, "Organisation Chain")
    if chain:
        record.raw["organisation_chain"] = chain
    if "captchaText" in html and not fields:
        record.raw["detail_blocked"] = "captcha"
    return record


def detail_is_captcha(html: str) -> bool:
    return 'name="captchaText"' in html or "Enter Captcha" in html


def session_is_stale(html: str) -> bool:
    lowered = html.lower()
    return "your session has timed out" in lowered or "stale session" in lowered


def _field(fields: dict[str, str], name: str) -> str:
    return fields.get(name, "")


def _field_prefix(fields: dict[str, str], prefix: str) -> str:
    for key, value in fields.items():
        if key.startswith(prefix):
            return value
    return ""


class TamilNaduAdapter:
    source = "tntenders"

    def __init__(self, client):
        self.client = client

    def fetch(self, ctx: CrawlContext) -> FetchResult:
        errors: list[str] = []
        records: list[RawTender] = []
        marker = dict(ctx.marker or {})
        org_counts = dict(marker.get("org_counts") or {})
        try:
            index_html, index_url = self._get_index()
        except (HttpStatusError, RobotsDisallowed) as exc:
            return FetchResult(
                records=[],
                awards=[],
                errors=[str(exc)],
                http_requests=self.client.requests_made,
                marker=marker,
            )
        orgs = parse_org_index(index_html, index_url)
        if not orgs:
            errors.append("Tamil Nadu organisation index returned no organisations.")
        ordered = sorted(orgs, key=lambda org: (org.count, org.name.lower()))
        offset = 0 if ctx.full or not ordered else int(marker.get("org_offset") or 0) % len(ordered)
        details_left = ctx.max_details
        visited = 0
        scanned = 0
        captcha_details = False
        while ordered and visited < ctx.max_orgs and scanned < len(ordered):
            org = ordered[(offset + scanned) % len(ordered)]
            scanned += 1
            previous = org_counts.get(org.name)
            if not ctx.full and previous == org.count:
                continue
            list_html = self._get_org_list(org, errors)
            if list_html is None:
                # Refresh the index once and retry this organisation with a new link.
                try:
                    index_html, index_url = self._get_index()
                    refreshed = {item.name: item for item in parse_org_index(index_html, index_url)}
                    if org.name in refreshed:
                        org = refreshed[org.name]
                        list_html = self._get_org_list(org, errors)
                except (HttpStatusError, RobotsDisallowed) as exc:
                    errors.append(str(exc))
            if list_html is None:
                continue
            rows = parse_tn_tender_list(list_html, org.url)
            complete = len(rows) >= org.count
            if not complete:
                errors.append(
                    f"{org.name} lists {org.count} tenders but the page contained "
                    f"{len(rows)}. The cursor is not advanced for this organisation, "
                    "so a later run will try it again. No extra pages were invented."
                )
            for row in rows:
                if details_left <= 0 or captcha_details or not row.detail_url:
                    records.append(row)
                    continue
                try:
                    detail = self.client.get(row.detail_url)
                except (HttpStatusError, RobotsDisallowed) as exc:
                    errors.append(f"Detail for {row.source_key} failed: {exc}")
                    records.append(row)
                    continue
                details_left -= 1
                if detail_is_captcha(detail.text):
                    captcha_details = True
                    errors.append(
                        "Tamil Nadu tender detail is captcha-gated; remaining details "
                        "were not requested."
                    )
                    records.append(row)
                    continue
                records.append(apply_tn_detail(row, detail.text))
            if complete:
                org_counts[org.name] = org.count
            visited += 1

        award_note = self._probe_awards()
        if award_note:
            errors.append(award_note)
        if ordered:
            marker["org_offset"] = (offset + scanned) % len(ordered)
        marker["org_counts"] = org_counts
        return FetchResult(
            records=records,
            awards=[],
            errors=errors,
            http_requests=self.client.requests_made,
            marker=marker,
            portal_reported_totals={
                "tntenders_orgs": len(orgs),
                "tntenders_listed": sum(o.count for o in orgs),
            },
        )

    def _get_index(self):
        response = self.client.get(ORG_INDEX)
        return response.text, response.url

    def _get_org_list(self, org: OrgRef, errors: list[str]) -> str | None:
        try:
            response = self.client.get(org.url, headers={"Referer": ORG_INDEX})
        except (HttpStatusError, RobotsDisallowed) as exc:
            errors.append(f"{org.name}: {exc}")
            return None
        if session_is_stale(response.text):
            errors.append(
                f"{org.name}: session expired before the organisation list could be read."
            )
            return None
        return response.text

    def _probe_awards(self) -> str | None:
        try:
            response = self.client.get(RESULTS, attempts=1)
        except (HttpStatusError, RobotsDisallowed) as exc:
            return f"Tamil Nadu results page was not read ({exc})."
        if detail_is_captcha(response.text) or 'name="captchaText"' in response.text:
            return (
                "Tamil Nadu Result of Tenders is a captcha form. "
                "It was not submitted, so no award rows were collected from this portal."
            )
        return None
