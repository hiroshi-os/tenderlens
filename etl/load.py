from __future__ import annotations

from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.utils import timezone

from crawlers.merge import merge_records
from crawlers.parseutil import content_hash
from crawlers.types import RawAward, RawTender
from etl.normalize import buyer_identity, display_organisation, normalise_text
from tenders.models import Award, Buyer, Tender


@dataclass
class LoadStats:
    created_ids: list[int] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    awards_created: int = 0
    awards_updated: int = 0


def load_tenders(records: list[RawTender]) -> LoadStats:
    stats = LoadStats()
    now = timezone.now()
    for record in merge_records(records):
        buyer = _buyer_for(record)
        digest = content_hash(record)
        defaults = {
            "feed": record.feed,
            "title": (record.title or record.source_key)[:1000],
            "description": record.description or "",
            "reference_number": (record.reference_number or "")[:300],
            "buyer": buyer,
            "category": (record.category or "")[:400],
            "state": (record.state or buyer.state or "")[:100],
            "location": (record.location or "")[:300],
            "pincode": (record.pincode or "")[:12],
            "estimated_value_inr": record.estimated_value_inr,
            "emd_inr": record.emd_inr,
            "quantity": record.quantity,
            "is_high_value": record.is_high_value,
            "published_at": record.published_at,
            "deadline_at": record.deadline_at,
            "opening_at": record.opening_at,
            "status": _status(record),
            "detail_url": record.detail_url or "",
            "content_hash": digest,
            "raw": record.raw or {},
            "last_seen_at": now,
        }
        existing = Tender.objects.filter(source=record.source, source_key=record.source_key).first()
        if existing is None:
            tender = Tender.objects.create(
                source=record.source, source_key=record.source_key, **defaults
            )
            stats.created += 1
            stats.created_ids.append(tender.id)
            continue
        if existing.content_hash == digest:
            existing.last_seen_at = now
            existing.save(update_fields=["last_seen_at"])
            stats.unchanged += 1
            continue
        for key, value in defaults.items():
            setattr(existing, key, value)
        existing.save()
        stats.updated += 1
    return stats


def load_awards(awards: list[RawAward]) -> LoadStats:
    stats = LoadStats()
    for award in awards:
        buyer = None
        if award.organisation or award.department or award.ministry:
            buyer = _buyer_for_parts(
                award.organisation, award.department, award.ministry, award.state
            )
        tender = None
        if award.tender_source_key:
            tender = Tender.objects.filter(
                source=award.source, source_key=award.tender_source_key
            ).first()
        defaults = {
            "tender": tender,
            "buyer": buyer,
            "awardee_name": award.awardee_name[:400],
            "awardee_normalised": normalise_text(award.awardee_name)[:400],
            "awarded_value_inr": award.awarded_value_inr,
            "awarded_at": award.awarded_at,
            "state": (award.state or "")[:100],
            "detail_url": award.detail_url or "",
            "raw": award.raw or {},
        }
        _obj, created = Award.objects.update_or_create(
            source=award.source, source_key=award.source_key, defaults=defaults
        )
        if created:
            stats.awards_created += 1
        else:
            stats.awards_updated += 1
    return stats


def ingest(records: list[RawTender], awards: list[RawAward] | None = None) -> LoadStats:
    """Load rows and fan alerts out to tenders seen for the first time."""
    from alerts.evaluate import evaluate_alerts

    with transaction.atomic():
        stats = load_tenders(records)
        if awards:
            award_stats = load_awards(awards)
            stats.awards_created = award_stats.awards_created
            stats.awards_updated = award_stats.awards_updated
        evaluate_alerts(stats.created_ids)
    return stats


def _buyer_for(record: RawTender) -> Buyer:
    return _buyer_for_parts(record.organisation, record.department, record.ministry, record.state)


def _buyer_for_parts(organisation: str, department: str, ministry: str, state: str) -> Buyer:
    organisation = display_organisation(organisation, department)
    identity = buyer_identity(
        organisation=organisation, department=department, ministry=ministry, state=state
    )
    try:
        buyer, _created = Buyer.objects.get_or_create(
            identity=identity,
            defaults={
                "organisation": organisation[:400],
                "department": (department or "")[:400],
                "ministry": (ministry or "")[:400],
                "state": (state or "")[:100],
            },
        )
    except IntegrityError:
        buyer = Buyer.objects.get(identity=identity)
    return buyer


def _status(record: RawTender) -> str:
    if record.deadline_at is not None and record.deadline_at < timezone.now():
        return Tender.Status.CLOSED
    return record.status or Tender.Status.ACTIVE
