from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F, QuerySet
from django.utils import timezone

from tenders.models import Tender

IST = ZoneInfo("Asia/Kolkata")


def tenders_matching(filters: dict, queryset: QuerySet | None = None) -> QuerySet:
    qs = queryset if queryset is not None else Tender.objects.all()
    qs = qs.select_related("buyer")
    keywords = (filters.get("q") or filters.get("keywords") or "").strip()
    if keywords:
        query = SearchQuery(keywords, config="english", search_type="websearch")
        qs = qs.filter(search_vector=query).annotate(rank=SearchRank(F("search_vector"), query))
        qs = qs.order_by("-rank", F("deadline_at").asc(nulls_last=True))
    else:
        qs = qs.order_by(
            F("deadline_at").asc(nulls_last=True), F("published_at").desc(nulls_last=True)
        )
    category = (filters.get("category") or "").strip()
    if category:
        qs = qs.filter(category__iexact=category)
    state = (filters.get("state") or "").strip()
    if state:
        qs = qs.filter(state__iexact=state)
    ministry = (filters.get("ministry") or "").strip()
    if ministry:
        qs = qs.filter(buyer__ministry__iexact=ministry)
    if filters.get("min_value") not in (None, ""):
        qs = qs.filter(estimated_value_inr__gte=filters["min_value"])
    if filters.get("max_value") not in (None, ""):
        qs = qs.filter(estimated_value_inr__lte=filters["max_value"])
    closing = filters.get("closing_before")
    if closing:
        if isinstance(closing, str):
            closing = datetime.strptime(closing, "%Y-%m-%d").date()
        end = datetime.combine(closing, time.max, tzinfo=IST)
        qs = qs.filter(deadline_at__lte=end)
    return qs


def closing_between(start, end) -> QuerySet:
    return (
        Tender.objects.filter(deadline_at__gte=start, deadline_at__lt=end)
        .select_related("buyer")
        .order_by("deadline_at")
    )


def aware(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, IST)
    return dt
