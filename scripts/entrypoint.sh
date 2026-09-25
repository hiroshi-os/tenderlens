#!/bin/sh
set -eu
python scripts/wait_for_db.py
python manage.py migrate --noinput
python manage.py load_recorded
python manage.py ensure_demo_user
python manage.py collectstatic --noinput
exec python manage.py runserver 0.0.0.0:8000
