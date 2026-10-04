"""Settings override used for the pytest suite.

Swaps the Postgres database for an in-memory SQLite DB so tests don't
depend on a running Postgres container. Imported via pytest.ini's
DJANGO_SETTINGS_MODULE.
"""

import os

# settings.py has no SECRET_KEY default, so the suite brings its own rather
# than depending on whatever key a developer's .env holds. Set before the
# import below, which is where it is read.
os.environ["SECRET_KEY"] = "test-only-secret-key-not-used-anywhere-else-0123456789"

from .settings import *  # noqa: E402,F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Nothing in the suite may reach a real service. These would otherwise be
# inherited from a developer's .env — which has held a live Stripe key.
# With no Shippo token, quoting raises ShippoNotConfigured and build_order
# takes its flat-rate fallback without a request; with no Stripe key, any
# unmocked Stripe call fails locally before sending anything.
SHIPPO_TOKEN = ""
STRIPE_SECRET_KEY = ""
STRIPE_PUBLIC_KEY = ""
OPENAI_API_KEY = ""
