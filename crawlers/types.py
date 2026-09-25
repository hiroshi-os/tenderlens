from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class RawTender:
    source: str
    source_key: str
    title: str
    feed: str
    description: str = ""
    reference_number: str = ""
    organisation: str = ""
    department: str = ""
    ministry: str = ""
    state: str = ""
    category: str = ""
    location: str = ""
    pincode: str = ""
    estimated_value_inr: Decimal | None = None
    emd_inr: Decimal | None = None
    quantity: int | None = None
    is_high_value: bool | None = None
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    opening_at: datetime | None = None
    detail_url: str = ""
    status: str = "active"
    raw: dict = field(default_factory=dict)

    def identity(self) -> tuple[str, str]:
        return (self.source, self.source_key)


@dataclass
class RawAward:
    source: str
    source_key: str
    awardee_name: str
    feed: str
    tender_source_key: str = ""
    organisation: str = ""
    department: str = ""
    ministry: str = ""
    state: str = ""
    awarded_value_inr: Decimal | None = None
    awarded_at: datetime | None = None
    detail_url: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class OrgRef:
    name: str
    count: int
    url: str


@dataclass
class CrawlContext:
    marker: dict
    max_pages: int = 2
    max_orgs: int = 5
    max_details: int = 10
    full: bool = False


@dataclass
class FetchResult:
    records: list[RawTender]
    awards: list[RawAward]
    errors: list[str]
    http_requests: int
    marker: dict
    portal_reported_totals: dict = field(default_factory=dict)
