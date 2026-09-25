from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")

TENDER_ID_RE = re.compile(r"\b(20\d{2}_[A-Za-z0-9]+_\d+_\d+)\b")
GEM_BID_RE = re.compile(r"\b(GEM/\d{4}/[A-Z]/\d+)\b", re.I)
PAGE_RE = re.compile(r"[?&]page=(\d+)")
MONEY_RE = re.compile(
    r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(crore|cr|lakh|lac|lakhs)?",
    re.I,
)


def parse_portal_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = " ".join(value.replace(".", "").split())
    for fmt in ("%d-%b-%Y %I:%M %p", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def parse_inr(value: str | int | float | None, *, zero_as_missing: bool = True) -> Decimal | None:
    """Parse a portal money string. Zero is treated as unpublished, not as free."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        amount = Decimal(str(value))
        if zero_as_missing and amount == 0:
            return None
        return amount.quantize(Decimal("0.01"))
    text = value.replace("₹", " ").replace("Rs", " ").replace("INR", " ")
    text = text.replace("\xa0", " ").strip()
    if not text or text in {"-", "--", "NA", "N/A", "Nil"}:
        return None
    match = MONEY_RE.search(text)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    unit = (match.group(2) or "").lower()
    if unit in {"crore", "cr"}:
        amount *= Decimal("10000000")
    elif unit in {"lakh", "lac", "lakhs"}:
        amount *= Decimal("100000")
    if zero_as_missing and amount == 0:
        return None
    return amount.quantize(Decimal("0.01"))


def first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text or "")
    return match.group(1) if match else ""


def clean_text(value: str | None) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def data_rows(html: str):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="table") or soup.find("table")
    if table is None:
        return soup, []
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if cells:
            rows.append(cells)
    return soup, rows


def cell_text(cell) -> str:
    return clean_text(cell.get_text(" ", strip=True))


def absolute(base: str, href: str | None) -> str:
    if not href:
        return ""
    return urljoin(base, href)


def next_numbered_page(html: str, current_url: str, current_page: int) -> str | None:
    """Follow the portal's own base64 ``url=`` pagination links."""
    soup = BeautifulSoup(html, "html.parser")
    target = current_page + 1
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        decoded = _decode_page_link(href)
        if decoded == target:
            return urljoin(current_url, href)
    return None


def _decode_page_link(href: str) -> int | None:
    match = re.search(r"[?&]url=([^&]+)", href)
    if not match:
        page = PAGE_RE.search(href)
        return int(page.group(1)) if page else None
    padded = unquote(match.group(1))
    padded += "=" * (-len(padded) % 4)
    try:
        decoded = base64.b64decode(padded).decode("utf-8", "replace")
    except (ValueError, UnicodeError):
        return None
    page = PAGE_RE.search(decoded)
    return int(page.group(1)) if page else None


def reported_total(html: str, label: str) -> int | None:
    match = re.search(rf"{label}\s*:?\s*([0-9,]+)", html, re.I)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def ministry_from_text(*parts: str) -> str:
    for part in parts:
        text = clean_text(part)
        if "ministry of" in text.lower():
            return text
    return ""


def content_hash(record) -> str:
    payload = {
        "title": record.title,
        "description": record.description,
        "reference_number": record.reference_number,
        "organisation": record.organisation,
        "department": record.department,
        "ministry": record.ministry,
        "state": record.state,
        "category": record.category,
        "estimated_value_inr": str(record.estimated_value_inr)
        if record.estimated_value_inr is not None
        else None,
        "emd_inr": str(record.emd_inr) if record.emd_inr is not None else None,
        "published_at": record.published_at.isoformat() if record.published_at else None,
        "deadline_at": record.deadline_at.isoformat() if record.deadline_at else None,
        "opening_at": record.opening_at.isoformat() if record.opening_at else None,
        "status": record.status,
        "detail_url": record.detail_url,
    }
    encoded = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def scrub_mapping(payload: dict) -> dict:
    """Drop buyer email fields before anything is stored."""
    cleaned = {}
    for key, value in payload.items():
        lowered = key.lower()
        if "email" in lowered or "created_by" in lowered:
            continue
        if isinstance(value, str) and "@" in value and " " not in value:
            continue
        cleaned[key] = value
    return cleaned


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_value(value):
    items = as_list(value)
    return items[0] if items else None
