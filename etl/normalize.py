from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")


def normalise_text(value: str | None) -> str:
    return _SPACE.sub(" ", (value or "").strip().lower())


def buyer_identity(*, organisation: str, department: str, ministry: str, state: str) -> str:
    parts = [
        normalise_text(ministry),
        normalise_text(department),
        normalise_text(organisation),
        normalise_text(state),
    ]
    return "|".join(parts)[:700]


def display_organisation(organisation: str, department: str) -> str:
    return organisation or department or "Unknown organisation"
