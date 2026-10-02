"""Set shipping weight and dimensions on candle variants.

Weights are measured, not guessed: see Shipping Label Estimate Weight.docx.
Poured candles are bare net weight; molded ones include their retail wrap,
because that wrap goes into the carton too. Box tare is added separately by
shipping.normalize.build_parcels from SHIPPO_BOXES.

Dimensions are close estimates. At this size and density the carrier prices on
actual weight, not dimensional weight, so half an inch either way does not move
the rate. Remeasure at leisure.

    python manage.py set_shipping_specs --dry-run
    python manage.py set_shipping_specs
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from candles.models import CandleVariant

# (label, matcher, weight_oz, length_in, width_in, height_in)
SPECS = [
    (
        "Литая 8 oz",
        Q(size__icontains="8 oz") | Q(size__icontains="8oz"),
        "18.20", "3.00", "3.00", "3.50",
    ),
    (
        "Литая 11.3 oz",
        Q(size__icontains="11.3") | Q(size__icontains="11.2"),
        "20.20", "3.50", "3.50", "4.00",
    ),
    (
        "Молдед малая",
        Q(size__icontains="small") | Q(size__icontains="малая"),
        "3.53", "2.00", "2.00", "2.50",
    ),
    (
        "Молдед большая",
        Q(size__icontains="large") | Q(size__icontains="большая"),
        "7.05", "3.00", "3.00", "3.50",
    ),
]


class Command(BaseCommand):
    help = "Assign shipping weight and dimensions to candle variants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be matched without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        touched = set()

        for label, matcher, weight, length, width, height in SPECS:
            variants = CandleVariant.objects.filter(matcher)

            if not variants.exists():
                self.stdout.write(self.style.WARNING(f"{label}: ничего не найдено"))
                continue

            self.stdout.write(f"\n{label} — {variants.count()} шт, {weight} oz")

            for variant in variants:
                marker = " (уже был обновлён выше!)" if variant.id in touched else ""
                self.stdout.write(f"  #{variant.id} {variant}{marker}")
                touched.add(variant.id)

            if dry_run:
                continue

            variants.update(
                weight_oz=Decimal(weight),
                length_in=Decimal(length),
                width_in=Decimal(width),
                height_in=Decimal(height),
            )

        missed = CandleVariant.objects.exclude(id__in=touched)

        if missed.exists():
            self.stdout.write(
                self.style.WARNING(f"\nНе подошли под фильтры — {missed.count()} шт:")
            )
            for variant in missed[:20]:
                self.stdout.write(f"  #{variant.id} size={variant.size!r} — {variant}")

        if dry_run:
            self.stdout.write(self.style.NOTICE("\nDry run, ничего не записано."))
        else:
            self.stdout.write(self.style.SUCCESS("\nГотово."))