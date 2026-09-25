# TenderLens runbook

TenderLens is a Django application. Production on Ubuntu is Nginx in front of uWSGI, with PostgreSQL, Redis, and a Celery worker. Celery beat is the scheduler. A cron line is in `deploy/cron/` if you would rather not run beat.

## Local demo

```bash
cp .env.example .env
docker compose up --build
```

Open http://localhost:8000. The entrypoint migrates, loads the recorded public pages in `tests/fixtures/`, and creates the demo user from `DEMO_PASSWORD`. Those fixtures are real portal HTML and JSON captured on 2026-09-25, not invented tenders. Log in as `demo` / `demo-tenderlens` (local only). The admin user is `admin` / `admin-tenderlens` when those variables are set.

Health: `curl -f http://localhost:8000/healthz`

A live crawl, from the web container or a venv pointed at the same database:

```bash
python manage.py crawl --max-pages 2 --max-orgs 4 --max-details 8 --delay 2
```

Do not lower `--delay` below 2 seconds against the public portals.

## Ubuntu host

Packages: `python3.12`, `python3.12-venv`, `postgresql`, `redis-server`, `nginx`, build tools for uWSGI (`gcc`, `python3-dev`).

```bash
sudo -u postgres createuser tenderlens
sudo -u postgres createdb -O tenderlens tenderlens
sudo mkdir -p /opt/tenderlens /var/lib/tenderlens /run/tenderlens
sudo chown www-data:www-data /var/lib/tenderlens /run/tenderlens
# copy the repo to /opt/tenderlens
python3.12 -m venv /opt/tenderlens/.venv
/opt/tenderlens/.venv/bin/pip install -r requirements-prod.txt
```

`/etc/tenderlens.env` (mode 640, group www-data) needs `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_SECURE=1`, `DATABASE_URL`, `REDIS_URL`, `DJANGO_ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`. Change the demo passwords before this file is installed; the values in `.env.example` are for the local compose file only.

```bash
sudo -u www-data /opt/tenderlens/.venv/bin/python manage.py migrate
sudo -u www-data /opt/tenderlens/.venv/bin/python manage.py load_recorded
sudo -u www-data /opt/tenderlens/.venv/bin/python manage.py collectstatic --noinput
sudo cp deploy/nginx/tenderlens.conf /etc/nginx/sites-available/tenderlens
sudo ln -sf /etc/nginx/sites-available/tenderlens /etc/nginx/sites-enabled/tenderlens
sudo cp deploy/systemd/tenderlens-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tenderlens-web tenderlens-worker tenderlens-beat
sudo nginx -t && sudo systemctl reload nginx
```

Put TLS in front of the Nginx `listen 80` server (certbot or your own certificate) before setting `DJANGO_SECURE=1`.

## What to check

| Check | Command |
| --- | --- |
| App | `curl -f http://127.0.0.1/healthz` |
| uWSGI | `systemctl status tenderlens-web` |
| Worker | `systemctl status tenderlens-worker` |
| Schedule | `systemctl status tenderlens-beat` |
| Last crawl | Django admin → Crawl runs, or `psql` on `tenders_crawlrun` |

`/healthz` returns 200 when PostgreSQL answers `SELECT 1`. Redis is reported in the JSON and does not by itself fail the check, because read traffic does not need the broker. A database failure returns 503.

## Crawl failures

Crawl runs record per-source errors on `CrawlRun.error` and still keep rows that were parsed. Typical recorded cases, not outages to "fix" by bypassing the portal:

- CPPP latest-active or award URLs returning HTTP 500.
- `bidplus.gem.gov.in` resetting TLS from a non-Indian network. The crawl continues with the CPPP GeM mirror and the GeM global JSON feed.
- Tamil Nadu "Result of Tenders" showing a captcha. The crawler does not submit it.
- A GePNIC direct link saying the session timed out. The organisation index is loaded again once.

Re-run with `python manage.py crawl`. Add `--full` to ignore the incremental cursor, still bounded by `--max-pages`, `--max-orgs`, and `--max-details`.

## Search index

The GIN index is `tender_search_gin` on `tenders_tender.search_vector`. A trigger fills the vector from title, description, and category. After a bulk SQL load that bypasses the ORM, run:

```sql
UPDATE tenders_tender SET title = title;
ANALYZE tenders_tender;
```

`python manage.py measure_search` drops that index, records `EXPLAIN (ANALYZE)`, and recreates it. Do not run it against a database that is serving traffic you care about; it takes a lock while the index is rebuilt.

## Rollback

```bash
sudo systemctl stop tenderlens-beat tenderlens-worker tenderlens-web
sudo -u postgres psql -d tenderlens -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION tenderlens;'
# redeploy the previous revision, then migrate and load_recorded again
```

`load_recorded` and `crawl` are idempotent on `(source, source_key)`. Restoring a SQL dump is preferable to the drop above when you have one.

## Logs

- Nginx: `/var/log/nginx/error.log`
- uWSGI and Celery: `journalctl -u tenderlens-web -u tenderlens-worker -u tenderlens-beat`
- Cron crawl, if used: `/var/log/tenderlens-crawl.log`
