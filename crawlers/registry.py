from __future__ import annotations

from crawlers.cppp import CpppAdapter
from crawlers.gem import GemAdapter
from crawlers.gepnnic import TamilNaduAdapter

SOURCES = ("cppp", "gem", "tntenders")


def build_adapters(client) -> dict:
    return {
        "cppp": CpppAdapter(client),
        "gem": GemAdapter(client),
        "tntenders": TamilNaduAdapter(client),
    }
