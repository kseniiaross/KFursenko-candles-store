from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from candles.models import Offer


def offer_applies_to(offer, candle) -> bool:
    """Whether this offer covers this candle.

    The link can be set from either side in the admin — Offer.candles and
    Candle.offers are separate tables — so both directions are checked.
    """
    if offer.apply_globally:
        return True

    if offer.candles.filter(pk=candle.pk).exists():
        return True

    if candle.offers.filter(pk=offer.pk).exists():
        return True

    if candle.category_id and offer.categories.filter(pk=candle.category_id).exists():
        return True

    collection_ids = candle.collections.values_list("pk", flat=True)

    return offer.collections.filter(pk__in=collection_ids).exists()


def get_welcome_offer(user):
    """The sign-up discount, if this shopper still qualifies.

    Resolved server-side on every request: a percentage sent by the
    storefront would be trivial to forge.
    """
    if not user or not user.is_authenticated:
        return None

    offer = (
        Offer.objects.filter(is_active=True, kind=Offer.Kind.NEW_SHOPPER)
        .order_by("priority")
        .first()
    )

    if not offer or not offer.discount_percent or not offer.is_currently_active:
        return None

    days = offer.new_shopper_days_active or 0

    if days and timezone.now() > user.created_at + timedelta(days=days):
        return None

    # Local import: orders.models reaches into candles, so pulling it in at
    # module level would close the loop.
    from .models import Order

    already_ordered = (
        Order.objects.filter(user=user)
        .exclude(status=Order.Status.CANCELED)
        .exists()
    )

    return None if already_ordered else offer


def has_competing_offer(candle, welcome_offer_id) -> bool:
    """True when the candle already carries a promotion of its own.

    Discounts do not stack: a candle on another offer keeps that one and
    skips the welcome percentage.
    """
    others = Offer.objects.filter(is_active=True).exclude(pk=welcome_offer_id)

    return any(
        offer.is_currently_active and offer_applies_to(offer, candle)
        for offer in others
    )


def welcome_percent_for(candle, welcome_offer) -> Decimal:
    """How much of the welcome discount this candle actually earns."""
    if not welcome_offer:
        return Decimal("0")

    if not offer_applies_to(welcome_offer, candle):
        return Decimal("0")

    if has_competing_offer(candle, welcome_offer.pk):
        return Decimal("0")

    return Decimal(welcome_offer.discount_percent)