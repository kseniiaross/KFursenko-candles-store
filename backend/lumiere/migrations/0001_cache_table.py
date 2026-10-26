"""The table behind CACHES in settings.py: throttle counters every gunicorn
worker shares, and Lumière's search cache.

Named here rather than read from settings, so the table exists wherever the
migrations run, including the test database (whose settings use the
in-memory cache).
"""

from django.core.management import call_command
from django.db import migrations

TABLE = "django_cache"


def create_table(apps, schema_editor):
    call_command(
        "createcachetable", TABLE, database=schema_editor.connection.alias, verbosity=0
    )


def drop_table(apps, schema_editor):
    schema_editor.execute(
        f"DROP TABLE IF EXISTS {schema_editor.quote_name(TABLE)}"
    )


class Migration(migrations.Migration):
    dependencies = []

    operations = [migrations.RunPython(create_table, drop_table)]
