"""Public-source tender adapters.

Each portal sits behind the same fetch interface. Network access, retries,
and robots.txt checks live in ``crawlers.http``. Parsers are pure functions
so tests can run on recorded pages.
"""
