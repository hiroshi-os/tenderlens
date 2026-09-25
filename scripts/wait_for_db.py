import os
import sys
import time
from urllib.parse import urlparse

import psycopg


def main() -> None:
    url = os.environ.get("DATABASE_URL", "")
    parsed = urlparse(url)
    deadline = time.monotonic() + 60
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(
                dbname=parsed.path.lstrip("/"),
                user=parsed.username,
                password=parsed.password,
                host=parsed.hostname,
                port=parsed.port or 5432,
                connect_timeout=3,
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    print(f"database not ready: {last_error}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
