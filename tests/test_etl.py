from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from crawlers.types import RawAward, RawTender
from etl.load import ingest, load_awards, load_tenders
from tenders.models import Award, Buyer, Tender

pytestmark = pytest.mark.django_db


def _row(**overrides):
    data = dict(
        source="cppp",
        source_key="2026_TEST_1_1",
        feed="cppp_global",
        title="Road resurfacing on NH 48",
        description="Resurfacing work",
        organisation="National Highways Authority",
        ministry="Ministry of Road Transport and Highways",
        state="Rajasthan",
        category="Civil Works - Highways",
        estimated_value_inr=Decimal("2500000.00"),
        emd_inr=Decimal("50000.00"),
        published_at=datetime(2026, 9, 1, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        deadline_at=datetime(2026, 10, 15, 17, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    data.update(overrides)
    return RawTender(**data)


def test_load_dedups_on_source_key_and_normalises_the_buyer():
    first = load_tenders([_row(), _row()])
    assert first.created == 1
    assert Tender.objects.count() == 1
    buyer = Buyer.objects.get()
    assert buyer.ministry == "Ministry of Road Transport and Highways"
    assert buyer.state == "Rajasthan"
    second = load_tenders([_row()])
    assert second.created == 0
    assert second.unchanged == 1
    changed = load_tenders([_row(title="Road resurfacing on NH 48, package 2")])
    assert changed.updated == 1
    assert Tender.objects.count() == 1
    tender = Tender.objects.get()
    assert tender.search_vector is not None


def test_award_dedup_links_an_existing_tender():
    load_tenders([_row()])
    award = RawAward(
        source="cppp",
        source_key="award-1",
        awardee_name="Sharma Constructions",
        feed="manual",
        tender_source_key="2026_TEST_1_1",
        organisation="National Highways Authority",
        ministry="Ministry of Road Transport and Highways",
        state="Rajasthan",
        awarded_value_inr=Decimal("2400000.00"),
    )
    load_awards([award])
    load_awards([award])
    assert Award.objects.count() == 1
    stored = Award.objects.get()
    assert stored.tender.source_key == "2026_TEST_1_1"
    assert stored.awardee_normalised == "sharma constructions"


def test_ingest_is_idempotent():
    ingest([_row()])
    ingest([_row()])
    assert Tender.objects.count() == 1
