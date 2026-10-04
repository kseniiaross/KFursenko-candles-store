"""Cancel checkouts nobody finished, and put their stock back.

build_order reserves stock the moment an order is created, before payment.
A shopper who closes the tab, or whose card is declined and who gives up,
leaves a PENDING order holding that stock indefinitely — the catalogue then
shows candles as sold out that are sitting on the shelf.

For each PENDING order older than the cutoff, the PaymentIntent is cancelled
first and the order second. An order whose payment Stripe reports as
succeeded or processing is skipped: the webhook will settle it. An intent
Stripe has never heard of (404) counts as nothing to cancel.

That last rule has one dangerous reading: a STRIPE_SECRET_KEY for the wrong
account makes *every* intent 404, and the run would cancel orders whose
payments went through. So before cancelling anything, the run looks each
intent up (read-only) and stops — exit status 1, nothing changed — if too
large a share of them is missing. A few old test-mode orders among many
real ones pass; all of them missing does not.

    python manage.py expire_pending_orders                  # older than 2h
    python manage.py expire_pending_orders --older-than 90m
    python manage.py expire_pending_orders --dry-run        # no Stripe calls
    python manage.py expire_pending_orders --max-missing-ratio 1
                                     # these really are abandoned test orders

Meant to run on a schedule (a Railway cron service, every 15 minutes or so).
"""

import logging
import re
from datetime import timedelta

import stripe
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from orders.models import Order
from orders.payments import IntentRelease, cancel_pending_order, intent_exists

logger = logging.getLogger(__name__)

DURATION = re.compile(r"^(\d+)([mh])$")


def parse_duration(value: str) -> timedelta:
    match = DURATION.match(value.strip())

    if not match:
        raise CommandError(f"--older-than takes minutes or hours, e.g. 90m or 2h, not {value!r}")

    amount, unit = int(match.group(1)), match.group(2)

    return timedelta(minutes=amount) if unit == "m" else timedelta(hours=amount)


class Command(BaseCommand):
    help = "Cancel PENDING orders older than a cutoff and return their stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than",
            default="2h",
            help="Age after which an unpaid order is abandoned (e.g. 90m, 2h). Default 2h.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be cancelled without changing anything or calling Stripe.",
        )
        parser.add_argument(
            "--max-missing-ratio",
            type=float,
            default=0.5,
            help=(
                "Stop without cancelling anything if more than this share of the "
                "stale orders' PaymentIntents don't exist under the current key. "
                "Default 0.5."
            ),
        )
        parser.add_argument(
            "--min-sample",
            type=int,
            default=5,
            help=(
                "Only apply --max-missing-ratio once at least this many intents "
                "were looked up; a handful of old test orders would otherwise "
                "read as 100%% missing. Default 5."
            ),
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - parse_duration(options["older_than"])

        stale = list(
            Order.objects.filter(
                status=Order.Status.PENDING, created_at__lt=cutoff
            ).order_by("created_at")
        )

        if options["dry_run"]:
            for order in stale:
                self.stdout.write(f"would cancel order #{order.pk} ({order.created_at:%Y-%m-%d %H:%M})")
            return

        self._check_stripe_key(stale, options["max_missing_ratio"], options["min_sample"])

        cancelled = skipped = failed = 0

        for order in stale:
            try:
                outcome = cancel_pending_order(order)
            except ValueError:
                # Paid or cancelled since the query ran.
                skipped += 1
                continue
            except stripe.StripeError as error:
                # Stripe unreachable: leave it for the next run.
                failed += 1
                self.stderr.write(f"order #{order.pk}: Stripe error, left as is ({error})")
                continue

            if outcome is IntentRelease.IN_PROGRESS:
                skipped += 1
                self.stdout.write(f"order #{order.pk}: payment in progress, left for the webhook")
                continue

            cancelled += 1

        self.stdout.write(
            f"cancelled {cancelled}, skipped {skipped}, Stripe errors {failed}"
        )

    def _check_stripe_key(self, stale, max_ratio, min_sample):
        """Refuse to run if the key looks wrong, before anything changes.

        Lookups Stripe couldn't answer (network, 5xx) are left out of the
        ratio: they say nothing about the key, and those orders are skipped
        by the cancel loop anyway.
        """
        checked = missing = 0

        for order in stale:
            if not order.stripe_payment_intent_id:
                continue

            try:
                exists = intent_exists(order.stripe_payment_intent_id)
            except stripe.StripeError:
                continue

            checked += 1
            missing += 0 if exists else 1

        if checked < min_sample or missing / checked <= max_ratio:
            if missing:
                self.stdout.write(
                    f"{missing} of {checked} intents not found under the current key "
                    f"— within the {max_ratio:.0%} limit, treating them as old or "
                    "test-mode intents"
                )
            return

        message = (
            f"STOPPED: {missing} of {checked} stale orders' PaymentIntents do not "
            f"exist under the current STRIPE_SECRET_KEY ({missing / checked:.0%}, "
            f"limit {max_ratio:.0%}). That looks like a wrong or wrong-account key, "
            "not old test orders. No orders were cancelled. Check STRIPE_SECRET_KEY; "
            "if these really are abandoned test-mode orders, re-run with "
            "--max-missing-ratio 1."
        )
        logger.error(message)
        # CommandError prints to stderr and exits with status 1, so the cron
        # run shows as failed in Railway rather than as a quiet log line.
        raise CommandError(message)
