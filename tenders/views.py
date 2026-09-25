from __future__ import annotations

import calendar
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import login
from django.core.paginator import Paginator
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from dashboard.charts import bar_chart
from tenders.forms import SearchForm, SignupForm
from tenders.models import Award, Tender
from tenders.queries import (
    award_totals,
    deadlines_ahead,
    published_value_count,
    spend_by,
    volume_by_organisation,
)
from tenders.search import IST, closing_between, tenders_matching

PAGE_SIZE = 25


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created.")
        return redirect("home")
    return render(request, "registration/signup.html", {"form": form})


def tender_list(request):
    form = SearchForm(request.GET or None)
    filters = form.filters() if form.is_valid() else {}
    qs = (
        tenders_matching(filters)
        if filters
        else Tender.objects.select_related("buyer").order_by("deadline_at")
    )
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(
        request,
        "tenders/list.html",
        {
            "form": form,
            "page": page,
            "result_count": qs.count() if form.is_valid() else Tender.objects.count(),
        },
    )


def tender_detail(request, pk):
    tender = get_object_or_404(Tender.objects.select_related("buyer"), pk=pk)
    return render(request, "tenders/detail.html", {"tender": tender})


def dashboard(request):
    context = {
        "tender_count": Tender.objects.count(),
        "valued_count": published_value_count(),
        "volume": volume_by_organisation(),
        "spend_ministry": spend_by("buyer__ministry"),
        "spend_state": spend_by("state"),
        "deadlines": deadlines_ahead(),
        "award_count": Award.objects.count(),
    }
    return render(request, "tenders/dashboard.html", context)


@require_GET
def chart(request, kind: str):
    builders = {
        "organisations": _org_chart,
        "spend-ministry": _spend_ministry_chart,
        "spend-state": _spend_state_chart,
        "deadlines": _deadline_chart,
        "awardees": _award_chart,
    }
    builder = builders.get(kind)
    if builder is None:
        return HttpResponse(status=404)
    return HttpResponse(builder(), content_type="image/png")


def calendar_view(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        year, month = today.year, today.month
    start = datetime(year, month, 1, tzinfo=IST)
    end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1, tzinfo=IST)
    by_day: dict = {}
    for tender in closing_between(start, end):
        day = timezone.localtime(tender.deadline_at, IST).date()
        by_day.setdefault(day, []).append(tender)
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        weeks.append(
            [
                {
                    "date": day,
                    "in_month": day.month == month,
                    "tenders": by_day.get(day, []),
                }
                for day in week
            ]
        )
    previous = (year - 1, 12) if month == 1 else (year, month - 1)
    nxt = (year + 1, 1) if month == 12 else (year, month + 1)
    return render(
        request,
        "tenders/calendar.html",
        {
            "weeks": weeks,
            "year": year,
            "month": month,
            "label": start.strftime("%B %Y"),
            "previous": previous,
            "next": nxt,
        },
    )


def awards(request):
    rows = award_totals()
    recent = Award.objects.select_related("buyer", "tender").order_by("-awarded_at", "-id")[:50]
    return render(request, "tenders/awards.html", {"rows": rows, "recent": recent})


@require_GET
def healthz(request):
    from django.http import JsonResponse

    db_ok = False
    db_error = ""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_ok = True
    except Exception as exc:
        db_error = str(exc)[:200]
    redis_ok = None
    from django.conf import settings

    if settings.REDIS_URL:
        try:
            import redis

            redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1).ping()
            redis_ok = True
        except Exception:
            redis_ok = False
    body = {"status": "ok" if db_ok else "degraded", "db": db_ok, "redis": redis_ok}
    if db_error:
        body["db_error"] = db_error
    return JsonResponse(body, status=200 if db_ok else 503)


def _org_chart() -> bytes:
    rows = volume_by_organisation()
    return bar_chart(
        [row["buyer__organisation"] or "Unknown" for row in rows],
        [row["n"] for row in rows],
        "Listings by organisation",
        "Tenders",
    )


def _spend_ministry_chart() -> bytes:
    rows = [row for row in spend_by("buyer__ministry") if row["buyer__ministry"]]
    return bar_chart(
        [row["buyer__ministry"] for row in rows],
        [float(row["total"]) for row in rows],
        "Published estimated value by ministry",
        "INR",
    )


def _spend_state_chart() -> bytes:
    rows = [row for row in spend_by("state") if row["state"]]
    return bar_chart(
        [row["state"] for row in rows],
        [float(row["total"]) for row in rows],
        "Published estimated value by state",
        "INR",
    )


def _deadline_chart() -> bytes:
    rows = deadlines_ahead()
    return bar_chart(
        [row["day"].strftime("%d %b") for row in rows],
        [row["n"] for row in rows],
        "Deadlines in the next 14 days",
        "Tenders",
    )


def _award_chart() -> bytes:
    rows = award_totals()
    return bar_chart(
        [row["awardee_name"] for row in rows],
        [row["n"] for row in rows],
        "Award rows by supplier",
        "Awards",
    )
