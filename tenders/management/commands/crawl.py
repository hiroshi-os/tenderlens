from django.core.management.base import BaseCommand

from crawlers.registry import SOURCES
from etl.pipeline import run_all


class Command(BaseCommand):
    help = "Fetch public tender listings and load them into PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--source", action="append", choices=SOURCES, dest="sources")
        parser.add_argument("--max-pages", type=int, default=None)
        parser.add_argument("--max-orgs", type=int, default=None)
        parser.add_argument("--max-details", type=int, default=None)
        parser.add_argument("--delay", type=float, default=None)
        parser.add_argument(
            "--full",
            action="store_true",
            help="Ignore the incremental cursor and read up to the page and organisation caps.",
        )

    def handle(self, *args, **options):
        summary = run_all(
            sources=options["sources"],
            max_pages=options["max_pages"],
            max_orgs=options["max_orgs"],
            max_details=options["max_details"],
            delay=options["delay"],
            full=options["full"],
        )
        for source, payload in summary.items():
            self.stdout.write(f"{source}: {payload}")
