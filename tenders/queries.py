from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from tenders.models import Award, Tender


def volume_by_organisation(limit: int = 12):
    return list(
        Tender.objects.values("buyer__organisation")
        .annotate(n=Count("id"))
        .order_by("-n", "buyer__organisation")[:limit]
    )


def spend_by(field: str, limit: int = 12):
    return list(
        Tender.objects.exclude(estimated_value_inr__isnull=True)
        .values(field)
        .annotate(total=Sum("estimated_value_inr"), n=Count("id"))
        .order_by("-total")[:limit]
    )


def deadlines_ahead(days: int = 14):
    start = timezone.now()
    end = start + timedelta(days=days)
    rows = (
        Tender.objects.filter(deadline_at__gte=start, deadline_at__lt=end)
        .values("deadline_at__date")
        .annotate(n=Count("id"))
        .order_by("deadline_at__date")
    )
    return [{"day": row["deadline_at__date"], "n": row["n"]} for row in rows]


def award_totals(limit: int = 12):
    return list(
        Award.objects.values("awardee_name")
        .annotate(n=Count("id"), total=Sum("awarded_value_inr"))
        .order_by("-n", "awardee_name")[:limit]
    )


def published_value_count() -> int:
    return Tender.objects.exclude(estimated_value_inr__isnull=True).count()
