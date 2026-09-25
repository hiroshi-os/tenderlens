from __future__ import annotations

from crawlers.types import RawTender


def merge_records(records: list[RawTender]) -> list[RawTender]:
    """Collapse the same source key, filling blank fields from the other copy."""
    merged: dict[tuple[str, str], RawTender] = {}
    for record in records:
        key = record.identity()
        current = merged.get(key)
        if current is None:
            merged[key] = record
            continue
        merged[key] = _fill(current, record)
    return list(merged.values())


def _fill(primary: RawTender, secondary: RawTender) -> RawTender:
    # Prefer the copy that already has a published value or EMD.
    if primary.estimated_value_inr is None and secondary.estimated_value_inr is not None:
        primary, secondary = secondary, primary
    elif (
        primary.emd_inr is None
        and secondary.emd_inr is not None
        and primary.estimated_value_inr is None
    ):
        primary, secondary = secondary, primary
    for name in (
        "title",
        "description",
        "reference_number",
        "organisation",
        "department",
        "ministry",
        "state",
        "category",
        "location",
        "pincode",
        "detail_url",
    ):
        if not getattr(primary, name) and getattr(secondary, name):
            setattr(primary, name, getattr(secondary, name))
    if primary.estimated_value_inr is None:
        primary.estimated_value_inr = secondary.estimated_value_inr
    if primary.emd_inr is None:
        primary.emd_inr = secondary.emd_inr
    if primary.quantity is None:
        primary.quantity = secondary.quantity
    if primary.is_high_value is None:
        primary.is_high_value = secondary.is_high_value
    if primary.published_at is None:
        primary.published_at = secondary.published_at
    if primary.deadline_at is None:
        primary.deadline_at = secondary.deadline_at
    if primary.opening_at is None:
        primary.opening_at = secondary.opening_at
    primary.raw = {**secondary.raw, **primary.raw, "feeds": sorted({primary.feed, secondary.feed})}
    return primary
