from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model

from crawlers.types import RawAward, RawTender
from etl.load import ingest, load_awards

pytestmark = pytest.mark.django_db


def _seed():
    ingest(
        [
            RawTender(
                source="tntenders",
                source_key="2026_AU_1_1",
                feed="tntenders",
                title="Operating bakery shop in the campus",
                description="Bakery services for students",
                organisation="Anna University",
                state="Tamil Nadu",
                category="Services",
                ministry="Ministry of Education",
                estimated_value_inr=Decimal("120000.00"),
                deadline_at=datetime(2026, 10, 5, 15, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
            )
        ]
    )
    load_awards(
        [
            RawAward(
                source="tntenders",
                source_key="award-demo",
                awardee_name="Campus Foods",
                feed="test",
                tender_source_key="2026_AU_1_1",
                organisation="Anna University",
                state="Tamil Nadu",
                awarded_value_inr=Decimal("100000.00"),
            )
        ]
    )


def test_health_and_public_pages(client):
    _seed()
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["db"] is True
    home = client.get("/?q=bakery")
    assert home.status_code == 200
    assert b"bakery" in home.content.lower()
    dashboard = client.get("/dashboard/")
    assert dashboard.status_code == 200
    assert b"Ministry of Education" in dashboard.content
    chart = client.get("/dashboard/chart/organisations.png")
    assert chart.status_code == 200
    assert chart.content.startswith(b"\x89PNG")
    calendar = client.get("/calendar/?year=2026&month=10")
    assert calendar.status_code == 200
    assert b"Operating bakery" in calendar.content
    awards = client.get("/awards/")
    assert awards.status_code == 200
    assert b"Campus Foods" in awards.content


def test_signup_saved_search_and_alert(client):
    _seed()
    response = client.post(
        "/accounts/signup/",
        {
            "username": "msme",
            "email": "msme@example.com",
            "password1": "tenderlens-test",
            "password2": "tenderlens-test",
        },
    )
    assert response.status_code == 302
    assert get_user_model().objects.filter(username="msme").exists()
    saved = client.post(
        "/searches/",
        {
            "name": "Campus food",
            "keywords": "bakery",
            "category": "",
            "state": "Tamil Nadu",
            "ministry": "",
        },
    )
    assert saved.status_code == 302
    listed = client.get("/searches/")
    assert b"Campus food" in listed.content
    alert = client.post(
        "/alerts/",
        {
            "name": "Food",
            "keywords": "bakery",
            "category": "",
            "state": "",
            "ministry": "",
            "channel": "in_app",
            "is_active": "on",
        },
    )
    assert alert.status_code == 302
    assert client.get("/alerts/").status_code == 200


def test_anonymous_cannot_save_a_search(client):
    response = client.get("/searches/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.url
