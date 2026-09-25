from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from alerts.backends import get_backend
from alerts.models import Alert, Notification
from tenders.models import Tender
from tenders.search import tenders_matching


def evaluate_alerts(tender_ids: list[int]) -> int:
    """Notify each active alert about tenders that are new in this ingest.

    Matching reuses the search filters a user already saved. Delivery goes
    through the backend registered for the alert's channel. A unique
    (alert, tender) row stops a later ingest from sending the same notice again.
    """
    if not tender_ids:
        Alert.objects.filter(is_active=True).update(last_evaluated_at=timezone.now())
        return 0
    fresh = Tender.objects.filter(id__in=tender_ids).select_related("buyer")
    sent = 0
    now = timezone.now()
    alerts = Alert.objects.filter(is_active=True).select_related("user", "saved_search")
    for alert in alerts:
        matches = tenders_matching(alert.effective_filters(), fresh)
        for tender in matches:
            if _deliver(alert, tender):
                sent += 1
        alert.last_evaluated_at = now
        alert.save(update_fields=["last_evaluated_at"])
    return sent


def _deliver(alert: Alert, tender: Tender) -> bool:
    deadline = ""
    if tender.deadline_at:
        deadline = tender.deadline_at.astimezone().strftime("%d %b %Y %H:%M %Z")
    title = f"Tender alert: {tender.title[:180]}"
    body = (
        f"{tender.title}\n"
        f"Buyer: {tender.buyer}\n"
        f"Source: {tender.get_source_display()} {tender.source_key}\n"
        f"Closes: {deadline or 'not published'}\n"
        f"{tender.detail_url}"
    )
    notification = Notification(
        user=alert.user,
        alert=alert,
        tender=tender,
        channel=alert.channel,
        title=title[:300],
        body=body,
    )
    try:
        backend = get_backend(alert.channel)
        backend.send(notification)
    except Exception as exc:
        notification.status = Notification.Status.FAILED
        notification.error = str(exc)[:1000]
    try:
        with transaction.atomic():
            notification.save()
    except IntegrityError:
        return False
    return notification.status == Notification.Status.SENT
