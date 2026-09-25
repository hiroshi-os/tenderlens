import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("tenderlens")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(name="tenders.crawl_sources")
def crawl_sources():
    from etl.pipeline import run_all

    return run_all()
