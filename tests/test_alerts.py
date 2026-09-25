from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from alerts.models import Alert, Notification
from crawlers.types import RawTender
from etl.load import ingest

pytestmark = pytest.mark.django_db


def test_keyword_alert_fans_out_once_per_new_tender():
    user = get_user_model().objects.create_user("vendor", "vendor@example.com", "tenderlens-test")
    Alert.objects.create(
        user=user,
        name="Roads",
        keywords="resurfacing",
        channel=Alert.Channel.EMAIL,
    )
    record = RawTender(
        source="tntenders",
        source_key="2026_TN_1_1",
        feed="tntenders",
        title="Resurfacing of ward roads",
        description="Bituminous resurfacing",
        organisation="Municipal Corporation",
        state="Tamil Nadu",
        deadline_at=datetime(2026, 11, 2, 15, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        estimated_value_inr=Decimal("900000.00"),
    )
    ingest([record])
    ingest([record])
    notes = Notification.objects.filter(user=user)
    assert notes.count() == 1
    assert notes.get().status == Notification.Status.SENT
    assert len(mail.outbox) == 1
    assert "Resurfacing" in mail.outbox[0].subject


def test_unrelated_tender_does_not_notify():
    user = get_user_model().objects.create_user("vendor2", "v2@example.com", "tenderlens-test")
    Alert.objects.create(user=user, name="Bakery", keywords="bakery", channel=Alert.Channel.IN_APP)
    ingest(
        [
            RawTender(
                source="cppp",
                source_key="2026_X_1_1",
                feed="cppp_global",
                title="Supply of laboratory glassware",
                organisation="CSIR",
            )
        ]
    )
    assert Notification.objects.count() == 0
