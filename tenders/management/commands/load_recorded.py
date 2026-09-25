import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from crawlers.cppp import parse_cppp_global_html
from crawlers.gem import parse_gem_json, parse_gem_mirror_html
from crawlers.gepnnic import apply_tn_detail, parse_tn_tender_list
from etl.load import ingest


class Command(BaseCommand):
    help = "Load the recorded public pages in tests/fixtures. Safe to run more than once."

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR) / "tests" / "fixtures"
        records = []
        records.extend(parse_cppp_global_html((root / "cppp_global_page1.html").read_text())[0])
        records.extend(parse_gem_mirror_html((root / "cppp_gem_page1.html").read_text())[0])
        records.extend(parse_gem_json(json.loads((root / "gem_global_page1.json").read_text()))[0])
        tamil_nadu = parse_tn_tender_list(
            (root / "tn_list.html").read_text(),
            "https://tntenders.gov.in/nicgep/app",
        )
        detail = (root / "tn_detail.html").read_text()
        records.extend(apply_tn_detail(row, detail) for row in tamil_nadu)
        stats = ingest(records)
        self.stdout.write(
            f"recorded fixtures: created={stats.created} updated={stats.updated} unchanged={stats.unchanged}"
        )
