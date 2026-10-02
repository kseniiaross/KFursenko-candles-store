"""Settings override used for the pytest suite.

Swaps the Postgres database for an in-memory SQLite DB so tests don't
depend on a running Postgres container. Imported via pytest.ini's
DJANGO_SETTINGS_MODULE.
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
