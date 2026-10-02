"""How much each line of an order is discounted, and why.

One promotion per line, never two. A candle carrying a campaign badge takes
that campaign's discount; a candle carrying none is where the sign-up
percentage lands. That is what makes a mixed basket behave sensibly: three
Spring candles get their free third, a Halloween candle gets its seasonal
percentage, and a plain candle still earns the welcome discount on a first
order. Resolving it per order instead would mean adding one ordinary candle
could shrink the total saving, which reads as a broken site.

Everything here runs server-side. A percentage or a rate sent by the
storefront would be trivial to forge.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from candles.models import Offer

CENT = Decimal("0.01")


@dataclass(frozen=True)
class LineDiscount:
    """What one order line saves, and the wording to show for it."""

    amount: Decimal
    label: str


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


# ======================================================
# OFFER MATCHING
# ======================================================
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


def get_active_offers():
    """Every offer running right now, cheapest priority first.

    is_currently_active checks dates in Python, so the queryset is
    evaluated once here rather than re-filtered per candle.
    """
    offers = (
        Offer.objects.filter(is_active=True)
        .prefetch_related("categories", "collections", "candles")
        .order_by("priority")
    )

    return [offer for offer in offers if offer.is_currently_active]


def campaign_offer_for(candle, offers):
    """The campaign this candle belongs to, if any.

    Excludes the sign-up discount, which is personal rather than a
    property of the candle. Lowest priority number wins, matching the
    ordering the admin sorts by.
    """
    for offer in offers:
        if offer.kind == Offer.Kind.NEW_SHOPPER:
            continue

        if offer_applies_to(offer, candle):
            return offer

    return None


# ======================================================
# WELCOME OFFER
# ======================================================
def get_welcome_offer(user):
    """The sign-up discount, if this shopper still qualifies."""
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


# ======================================================
# BUY 2, GET 3
# ======================================================
def _free_units(unit_prices: list[Decimal]) -> Decimal:
    """Value given away across a group of eligible units.

    Sorted dearest first, then every third unit is free — so each complete
    trio surrenders its cheapest member. Taking the N cheapest overall
    instead would quietly under-reward a large basket: six candles at
    10..60 would give away 30 rather than the 50 the customer is promised.

    A quantity of two earns nothing. That is the offer, not a bug.
    """
    ordered = sorted(unit_prices, reverse=True)

    return sum(
        (price for index, price in enumerate(ordered) if index % 3 == 2),
        Decimal("0.00"),
    )


def _apply_buy_two_get_three(offer, lines, discounts) -> bool:
    """Spread one B2G3 offer's saving across the lines that earned it.

    The saving belongs to a group of units, not to any single line, so it
    is distributed proportionally to what each line contributed. Without
    that, a refund of one line could not tell how much of the freebie to
    claw back.
    """
    group = [line for line in lines if line["campaign"] is offer]

    if not group:
        return False

    units: list[Decimal] = []

    for line in group:
        units.extend([line["unit_price"]] * line["quantity"])

    saving = _free_units(units)

    if saving <= 0:
        return False

    group_total = sum(
        (line["unit_price"] * line["quantity"] for line in group), Decimal("0.00")
    )

    if group_total <= 0:
        return False

    label = offer.title
    running = Decimal("0.00")

    for index, line in enumerate(group):
        line_total = line["unit_price"] * line["quantity"]

        if index == len(group) - 1:
            # Last line absorbs the rounding so the parts always sum to
            # the saving the shopper was shown.
            share = saving - running
        else:
            share = _round(saving * line_total / group_total)
            running += share

        discounts[line["variant_id"]] = LineDiscount(amount=share, label=label)

    return True


# ======================================================
# ENTRY POINT
# ======================================================
def compute_line_discounts(*, user, lines):
    """Work out the discount for every line of an order.

    `lines` is a list of dicts with variant_id, candle, unit_price and
    quantity. Returns (discounts_by_variant_id, summary_label).
    """
    offers = get_active_offers()
    welcome_offer = get_welcome_offer(user)

    enriched = [
        {
            "variant_id": line["variant_id"],
            "candle": line["candle"],
            "unit_price": Decimal(line["unit_price"]),
            "quantity": int(line["quantity"]),
            "campaign": campaign_offer_for(line["candle"], offers),
        }
        for line in lines
    ]

    discounts: dict[int, LineDiscount] = {}
    applied_labels: list[str] = []

    # --- Buy 2, get 3 ------------------------------------------------
    b2g3_offers = {
        line["campaign"]
        for line in enriched
        if line["campaign"] and line["campaign"].kind == Offer.Kind.B1G2
    }

    for offer in b2g3_offers:
        if _apply_buy_two_get_three(offer, enriched, discounts):
            applied_labels.append(offer.title)

    # --- Percentage campaigns ---------------------------------------
    for line in enriched:
        offer = line["campaign"]

        if not offer or offer.kind == Offer.Kind.B1G2:
            continue

        if not offer.discount_percent:
            continue

        line_total = line["unit_price"] * line["quantity"]
        amount = _round(line_total * Decimal(offer.discount_percent) / Decimal("100"))

        if amount > 0:
            discounts[line["variant_id"]] = LineDiscount(
                amount=amount, label=offer.title
            )

            if offer.title not in applied_labels:
                applied_labels.append(offer.title)

    # --- Welcome discount --------------------------------------------
    # Only lands on candles no campaign claimed. A candle already in a
    # promotion keeps that promotion; stacking the two would hand out
    # twenty percent on a single item.
    if welcome_offer and welcome_offer.discount_percent:
        percent = Decimal(welcome_offer.discount_percent)

        for line in enriched:
            if line["campaign"] is not None:
                continue

            if not offer_applies_to(welcome_offer, line["candle"]):
                continue

            line_total = line["unit_price"] * line["quantity"]
            amount = _round(line_total * percent / Decimal("100"))

            if amount > 0:
                discounts[line["variant_id"]] = LineDiscount(
                    amount=amount, label=welcome_offer.title
                )

                if welcome_offer.title not in applied_labels:
                    applied_labels.append(welcome_offer.title)

    summary_label = " + ".join(applied_labels)

    return discounts, summary_label


# ======================================================
# STOREFRONT HELPER
# ======================================================
def buy_two_get_three_progress(candles_in_cart):
    """How close each B2G3 group is to earning a free candle.

    Feeds the cart prompt: "add one more Spring candle and the cheapest of
    the three is free". `candles_in_cart` is a list of (candle, quantity).
    Returns a list of dicts, one per offer with an incomplete trio.
    """
    offers = get_active_offers()
    counts: dict[int, int] = defaultdict(int)
    by_id: dict[int, Offer] = {}

    for candle, quantity in candles_in_cart:
        offer = campaign_offer_for(candle, offers)

        if not offer or offer.kind != Offer.Kind.B1G2:
            continue

        counts[offer.pk] += int(quantity)
        by_id[offer.pk] = offer

    progress = []

    for offer_id, count in counts.items():
        remainder = count % 3

        # A remainder of zero means every candle is already in a complete
        # trio; nothing to nudge about.
        if remainder == 0:
            continue

        progress.append(
            {
                "offer": by_id[offer_id],
                "in_cart": count,
                "needed": 3 - remainder,
                "free_so_far": count // 3,
            }
        )

    return progress


# ======================================================
# BACKWARDS COMPATIBILITY
# ======================================================
def has_competing_offer(candle, welcome_offer_id) -> bool:
    """Kept for callers outside build_order. New code should read the
    campaign off compute_line_discounts instead."""
    others = Offer.objects.filter(is_active=True).exclude(pk=welcome_offer_id)

    return any(
        offer.is_currently_active and offer_applies_to(offer, candle)
        for offer in others
    )


def welcome_percent_for(candle, welcome_offer) -> Decimal:
    """Kept for backwards compatibility. build_order now uses
    compute_line_discounts, which handles campaigns as well."""
    if not welcome_offer:
        return Decimal("0")

    if not offer_applies_to(welcome_offer, candle):
        return Decimal("0")

    if has_competing_offer(candle, welcome_offer.pk):
        return Decimal("0")

    return Decimal(welcome_offer.discount_percent)