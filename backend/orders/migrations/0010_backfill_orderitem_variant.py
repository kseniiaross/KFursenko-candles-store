"""Backfill OrderItem.variant for rows created before the field existed.

Freezes today's answer (there is exactly one CandleVariant per Candle right
now — verified separately) rather than re-deriving it with .first() on every
future label purchase, which is the whole point of recording it explicitly.
"""

from django.db import migrations


def backfill_variant(apps, schema_editor):
    OrderItem = apps.get_model("orders", "OrderItem")
    CandleVariant = apps.get_model("candles", "CandleVariant")

    items = OrderItem.objects.filter(variant__isnull=True)

    for item in items:
        variant = (
            CandleVariant.objects.filter(candle_id=item.candle_id)
            .order_by("id")
            .first()
        )

        if variant is None:
            # Candle has no variant left to attribute this row to (e.g. it
            # was deleted since). Nothing to backfill — leave it null rather
            # than fail the whole migration over historic data.
            continue

        item.variant = variant
        item.save(update_fields=["variant"])


def noop_reverse(apps, schema_editor):
    """Nothing to undo: clearing `variant` back to null would lose no
    information the forward pass didn't derive from `candle` in the first
    place — it's re-derivable, not new data."""


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0009_orderitem_variant"),
    ]

    operations = [
        migrations.RunPython(backfill_variant, noop_reverse),
    ]
