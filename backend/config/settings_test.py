"""Settings override used for the pytest suite.

The suite runs on PostgreSQL, the database production runs on. SQLite
ignores row locks, so a locking query Postgres refuses passed every test
and failed every real checkout (see orders/test_create_intent.py).

Postgres comes from docker-compose's `db` service: `docker compose up -d db`.
pytest-django creates and drops its own `test_candles_db` there; the
development database is never touched. `TEST_DB=sqlite pytest` still runs
the suite without a container, but can't catch database-specific failures.

Imported via pytest.ini's DJANGO_SETTINGS_MODULE.
"""

import os

# settings.py has no SECRET_KEY default, so the suite brings its own rather
# than depending on whatever key a developer's .env holds. Set before the
# import below, which is where it is read.
os.environ["SECRET_KEY"] = "test-only-secret-key-not-used-anywhere-else-0123456789"

from .settings import *  # noqa: E402,F401,F403

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

if os.environ.get("TEST_DB", "postgres") == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
else:
    # Spelled out rather than inherited: settings.py prefers DATABASE_URL,
    # and a developer's .env may hold one for a real database. The test
    # run creates and drops a database, so it may only ever talk to a local
    # server. Defaults match docker-compose.yml.
    _host = os.environ.get("TEST_DB_HOST", "127.0.0.1")

    if _host not in ("127.0.0.1", "localhost", "::1"):
        raise ImproperlyConfigured(
            f"Tests only run against a local Postgres, not {_host!r}."
        )

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("TEST_DB_NAME", "candles_db"),
            "USER": os.environ.get("TEST_DB_USER", "candles_user"),
            "PASSWORD": os.environ.get("TEST_DB_PASSWORD", "candles_pass"),
            "HOST": _host,
            "PORT": os.environ.get("TEST_DB_PORT", "5433"),
            "TEST": {"NAME": "test_candles_db"},
        }
    }

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Production serves static files through WhiteNoise's manifest storage,
# which only works after collectstatic. Tests that render admin pages need
# the plain storage instead.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Nothing in the suite may reach a real service. These would otherwise be
# inherited from a developer's .env — which has held a live Stripe key.
# With no Shippo token, quoting raises ShippoNotConfigured and build_order
# takes its flat-rate fallback without a request; with no Stripe key, any
# unmocked Stripe call fails locally before sending anything.
SHIPPO_TOKEN = ""
STRIPE_SECRET_KEY = ""
STRIPE_PUBLIC_KEY = ""
OPENAI_API_KEY = ""
