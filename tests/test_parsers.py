import json
from decimal import Decimal
from pathlib import Path

from crawlers.cppp import parse_cppp_global_html
from crawlers.gem import parse_gem_json, parse_gem_mirror_html
from crawlers.gepnnic import apply_tn_detail, parse_org_index, parse_tn_tender_list
from crawlers.merge import merge_records
from crawlers.parseutil import next_numbered_page, parse_inr, parse_portal_datetime
from crawlers.types import RawTender

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_inr_parsing_treats_zero_and_blanks_as_missing():
    assert parse_inr("50,000") == Decimal("50000.00")
    assert parse_inr("1.5 crore") == Decimal("15000000.00")
    assert parse_inr("2 lakh") == Decimal("200000.00")
    assert parse_inr("0.00") is None
    assert parse_inr("Nil") is None
    assert parse_inr("") is None


def test_portal_dates_are_india_time():
    parsed = parse_portal_datetime("25-Sep-2026 06:00 PM")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.hour == 18
    assert parsed.day == 25


def test_cppp_global_fixture_extracts_tender_ids():
    html = (FIXTURES / "cppp_global_page1.html").read_text()
    records, _total = parse_cppp_global_html(html)
    keys = {row.source_key for row in records}
    assert "2026_DRDO_791201_1" in keys
    drdo = next(row for row in records if row.source_key == "2026_DRDO_791201_1")
    assert "Liquid Chromatograph" in drdo.title
    assert drdo.organisation.startswith("Department of Defence")
    assert drdo.detail_url.startswith("https://eprocure.gov.in/cppp/tendersfullview/")
    assert drdo.estimated_value_inr is None


def test_cppp_pagination_link_decodes_the_next_page():
    html = """
    <a href="https://eprocure.gov.in/cppp/globaltenders/cpppdata?url=aHR0cHM6Ly9lcHJvY3VyZS5nb3YuaW4vY3BwcC9nbG9iYWx0ZW5kZXJzL2NwcHBkYXRhP3BhZ2U9Mg%3D%3D">2</a>
    """
    nxt = next_numbered_page(html, "https://eprocure.gov.in/cppp/globaltenders", 1)
    assert nxt is not None
    assert "url=" in nxt


def test_gem_mirror_fixture_uses_bid_number_as_key():
    html = (FIXTURES / "cppp_gem_page1.html").read_text()
    records, _total = parse_gem_mirror_html(html)
    assert records
    assert all(row.source == "gem" for row in records)
    assert all(row.source_key.startswith("GEM/") for row in records)
    first = records[0]
    assert first.organisation
    assert first.published_at is not None
    assert first.deadline_at is not None


def test_gem_json_fixture_keeps_ministry_and_drops_email_fields():
    payload = json.loads((FIXTURES / "gem_global_page1.json").read_text())
    records, total = parse_gem_json(payload)
    assert total == 21
    assert len(records) == 2
    first = records[0]
    assert first.source_key == "GEM/2026/B/8071078"
    assert first.ministry == "Ministry of Defence"
    assert first.title == "Atomic Layer Deposition System"
    assert "created_by" not in first.raw
    assert "@" not in json.dumps(first.raw)


def test_tamil_nadu_org_list_and_detail():
    orgs = parse_org_index((FIXTURES / "tn_org.html").read_text())
    anna = next(org for org in orgs if org.name == "Anna University Chennai")
    assert anna.count == 1
    assert anna.url.startswith("https://tntenders.gov.in/")
    rows = parse_tn_tender_list(
        (FIXTURES / "tn_list.html").read_text(),
        "https://tntenders.gov.in/nicgep/app",
    )
    assert len(rows) == 1
    record = apply_tn_detail(rows[0], (FIXTURES / "tn_detail.html").read_text())
    assert record.source_key == "2026_AU_704171_1"
    assert record.state == "Tamil Nadu"
    assert record.emd_inr == Decimal("50000.00")
    assert record.estimated_value_inr is None
    assert "Bakery" in record.title
    assert record.category == "Services"


def test_merge_fills_blank_value_from_the_other_copy():
    thin = RawTender(source="gem", source_key="GEM/2026/B/1", title="Pipes", feed="gem_cppp_mirror")
    rich = RawTender(
        source="gem",
        source_key="GEM/2026/B/1",
        title="",
        feed="gem_json",
        ministry="Ministry of Defence",
        estimated_value_inr=Decimal("10.00"),
    )
    merged = merge_records([thin, rich])
    assert len(merged) == 1
    assert merged[0].ministry == "Ministry of Defence"
    assert merged[0].estimated_value_inr == Decimal("10.00")
    assert merged[0].title == "Pipes"
