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

from collections import defaultdict, deque
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
    # Units on this line given away by buy-two-get-three. `amount` is then
    # exactly that many at the line's unit price — the line shows "Free" or
    # "1 free", and the stored discount says the same thing.
    free_quantity: int = 0


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
        .prefetch_related(
            "categories",
            "collections",
            "candles",
            "reward_categories",
            "reward_collections",
            "reward_candles",
        )
        .order_by("priority", "pk")
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

    # Only an order that was paid for and went out uses up the welcome offer.
    # PENDING is an unpaid attempt (a typo fixed at checkout, a declined
    # card); CANCELED and REFUNDED never shipped — REFUNDED can only follow
    # PAID, never SHIPPED — so counting them would take the offer away
    # because of our own cancellation.
    already_ordered = Order.objects.filter(
        user=user,
        status__in=[
            Order.Status.PAID,
            Order.Status.SHIPPED,
            Order.Status.COMPLETED,
        ],
    ).exists()

    return None if already_ordered else offer


# ======================================================
# BUY 2, GET 3
# ======================================================
def has_reward_group(offer) -> bool:
    """Whether the offer names its own free candles. Cached on the offer,
    which get_active_offers loads once per request."""
    cached = getattr(offer, "_has_reward_group", None)

    if cached is None:
        cached = (
            offer.reward_categories.exists()
            or offer.reward_collections.exists()
            or offer.reward_candles.exists()
        )
        offer._has_reward_group = cached

    return cached


def offer_rewards(offer, candle) -> bool:
    """Whether this candle can be the free one in a buy-two-get-three offer.

    An offer without a reward group gives away the candles that qualify,
    exactly as before the group existed.
    """
    if not has_reward_group(offer):
        return offer_applies_to(offer, candle)

    if offer.reward_candles.filter(pk=candle.pk).exists():
        return True

    if (
        candle.category_id
        and offer.reward_categories.filter(pk=candle.category_id).exists()
    ):
        return True

    collection_ids = candle.collections.values_list("pk", flat=True)

    return offer.reward_collections.filter(pk__in=collection_ids).exists()


def reward_offer_for(candle, offers):
    """The buy-two-get-three offer that can give this candle away, for a
    candle no campaign claims. A candle in a campaign is never given away by
    a different one: it keeps its own promotion. Lowest priority number
    wins, as for campaigns."""
    for offer in offers:
        if offer.kind != Offer.Kind.B1G2 or not has_reward_group(offer):
            continue

        if offer_rewards(offer, candle):
            return offer

    return None


# How a unit can take part in one offer: it pays towards a free candle,
# it can be the free candle, or either. At a tie in price, payers come
# first so a free candle can lean on a payer of its own price.
PAYS, EITHER, FREE_ONLY = 0, 1, 2


def _free_units(runs) -> list[int]:
    """How many units of each run are free.

    `runs` are (unit_price, role, quantity), already sorted dearest first,
    payers first at a tie. A free unit needs two paying units that cost at
    least as much — the rule the offer has always had, where the cheapest
    of each three was free — and the most the shopper can save under that
    rule is what they get. When every unit is EITHER (an offer with no
    reward group) this gives exactly the old answer: sort dearest first,
    every third unit free.

    Walks the runs keeping, for each number of payers still unmatched, the
    best (saving in cents, free count per run) so far. Ties go to freeing
    dearer runs first, which keeps the old answer when several give the
    same saving. Payers beyond twice the free-able units still to come can
    never be used, so the count is capped there.
    """
    can_be_free_after = [0] * (len(runs) + 1)

    for index in range(len(runs) - 1, -1, -1):
        _, role, quantity = runs[index]
        can_be_free_after[index] = can_be_free_after[index + 1] + (
            quantity if role != PAYS else 0
        )

    # Index: unmatched payers. None: not reachable.
    best: list = [(0, ())]

    for index, (price, role, quantity) in enumerate(runs):
        cents = int(price * 100)

        if role == PAYS:
            step = [None] * quantity + [
                None if state is None else (state[0], state[1] + (0,))
                for state in best
            ]
        elif role == FREE_ONLY:
            # Each free unit uses two payers.
            step = _spread(best, stride=2, shift=0, quantity=quantity, cents=cents)
        else:
            # The run's other units pay, and can pay for its own free ones:
            # they cost the same. Each free unit is one payer fewer and uses
            # two.
            step = _spread(best, stride=3, shift=quantity, quantity=quantity, cents=cents)

        cap = 2 * can_be_free_after[index + 1]

        if len(step) > cap + 1:
            reachable = [state for state in step[cap:] if state is not None]
            step = step[:cap] + [max(reachable) if reachable else None]

        best = step

    return list(max(state for state in best if state is not None)[1])


def _spread(best, *, stride, shift, quantity, cents):
    """One run where up to `quantity` units can be free.

    Freeing x units with `p` unmatched payers leaves t = p + shift -
    stride * x. So the best result for each t is the best over a window of
    p, one residue class mod `stride` at a time — found with a sliding-window
    maximum, so a run costs time in proportion to the payer count rather
    than that times its quantity.
    """
    step = [None] * (len(best) + shift)

    for residue in range(stride):
        # p = (t - shift) + stride * x. Write t - shift = residue + stride * k;
        # then p = residue + stride * j for j in [k, k + quantity].
        highest = (len(best) - 1 - residue) // stride
        lowest = -((shift + residue) // stride)
        window: deque = deque()

        for k in range(highest, lowest - 1, -1):
            if k >= 0:
                p = residue + stride * k
                state = best[p]

                if state is not None:
                    # stride * (saving after freeing) differs from this by a
                    # constant for a given t, so the largest key wins; then
                    # the dearer-runs-first tie-break, then more freed here.
                    key = (stride * state[0] + p * cents, state[1], p)

                    while window and window[-1][0] < key:
                        window.pop()

                    window.append((key, k))

            while window and window[0][1] > k + quantity:
                window.popleft()

            if not window:
                continue

            (_, counts, p), j = window[0]
            free = j - k
            t = residue + stride * k + shift
            step[t] = (best[p][0] + free * cents, counts + (free,))

    return step


def _role(offer, line):
    """PAYS, EITHER or FREE_ONLY for this line in this offer; None when the
    offer doesn't count it. A line qualifies when the offer is its
    campaign; it can be free when it is in the offer's reward group (the
    qualifying candles, when the offer has none)."""
    qualifies = line["campaign"] is offer
    rewards = line["reward_offer"] is offer or (
        qualifies and offer_rewards(offer, line["candle"])
    )

    if qualifies and rewards:
        return EITHER
    if qualifies:
        return PAYS
    if rewards:
        return FREE_ONLY
    return None


def _apply_buy_two_get_three(offer, lines, discounts) -> bool:
    """Give one B2G3 offer's free units to the lines that hold them.

    Lines that qualify are the ones the offer claims as their campaign;
    lines that can be free are those in its reward group (the same lines,
    when it has none). The free units' own prices are the discount, on the
    lines those units sit on: a line with a free candle shows "Free" (or
    "1 free"), and the stored discount says exactly the same.

    Which unit is free when several share the free price is decided by
    variant id, highest first — never by basket order, which differs
    between a guest's browser, the server cart and the merge on sign-in.
    The same basket therefore marks the same candle free in the cart, at
    checkout and on the stored order.
    """
    roles = {}

    for line in lines:
        role = _role(offer, line)

        if role is not None:
            roles[line["variant_id"]] = role

    group = [line for line in lines if line["variant_id"] in roles]

    if not group:
        return False

    # Highest variant id first within a run: those lines take its free units.
    run_lines: dict[tuple[Decimal, int], list[dict]] = defaultdict(list)

    for line in sorted(group, key=lambda line: line["variant_id"], reverse=True):
        run_lines[(line["unit_price"], roles[line["variant_id"]])].append(line)

    keys = sorted(run_lines, key=lambda key: (-key[0], key[1]))
    runs = [
        (price, role, sum(line["quantity"] for line in run_lines[(price, role)]))
        for price, role in keys
    ]

    free_per_run = _free_units(runs)

    if not any(free_per_run):
        return False

    for key, free in zip(keys, free_per_run):
        for line in run_lines[key]:
            if not free:
                break

            count = min(free, line["quantity"])
            free -= count

            discounts[line["variant_id"]] = LineDiscount(
                amount=_round(line["unit_price"] * count),
                label=offer.title,
                free_quantity=count,
            )

    return True


@dataclass(frozen=True)
class OfferStanding:
    """Where a basket stands with one buy-two-get-three offer."""

    # Units in the basket the offer counts, as payer or free candle.
    in_offer: int
    # Of those, units that can pay towards a free one.
    can_pay: int
    # Of those, units that can be the free one.
    can_be_free: int
    free: int


def offer_standing(*, offer, lines, offers) -> OfferStanding:
    """How many units this offer makes free in this basket, and what it is
    working with. Same rule as checkout: it runs the same allocation.
    `lines` as for compute_line_discounts."""
    enriched = _enrich(lines, offers)
    discounts: dict[int, LineDiscount] = {}

    _apply_buy_two_get_three(offer, enriched, discounts)

    in_offer = can_pay = can_be_free = 0

    for line in enriched:
        role = _role(offer, line)

        if role is None:
            continue

        in_offer += line["quantity"]
        can_pay += line["quantity"] if role != FREE_ONLY else 0
        can_be_free += line["quantity"] if role != PAYS else 0

    return OfferStanding(
        in_offer=in_offer,
        can_pay=can_pay,
        can_be_free=can_be_free,
        free=sum(d.free_quantity for d in discounts.values()),
    )


# ======================================================
# ENTRY POINT
# ======================================================
_RESOLVE = object()


def _enrich(lines, offers):
    """Each line with the campaign that claims it and, for a line no
    campaign claims, the buy-two-get-three offer that can give it away."""
    enriched = []

    for line in lines:
        campaign = campaign_offer_for(line["candle"], offers)

        enriched.append(
            {
                "variant_id": line["variant_id"],
                "candle": line["candle"],
                "unit_price": Decimal(line["unit_price"]),
                "quantity": int(line["quantity"]),
                "campaign": campaign,
                "reward_offer": (
                    None
                    if campaign is not None
                    else reward_offer_for(line["candle"], offers)
                ),
            }
        )

    return enriched


def compute_line_discounts(*, user, lines, offers=None, welcome_offer=_RESOLVE):
    """Work out the discount for every line of an order.

    `lines` is a list of dicts with variant_id, candle, unit_price and
    quantity. Returns (discounts_by_variant_id, summary_label).

    `offers` and `welcome_offer` are looked up when not given. Callers that
    price many baskets for one shopper (a catalogue page) pass them in so the
    lookups run once. `welcome_offer=None` means "this shopper gets none",
    which is why "not given" needs its own sentinel.
    """
    if offers is None:
        offers = get_active_offers()
    if welcome_offer is _RESOLVE:
        welcome_offer = get_welcome_offer(user)

    enriched = _enrich(lines, offers)

    discounts: dict[int, LineDiscount] = {}
    applied_labels: list[str] = []

    # --- Buy 2, get 3 ------------------------------------------------
    b2g3_offers = [
        offer
        for offer in offers
        if offer.kind == Offer.Kind.B1G2
        and any(
            line["campaign"] is offer or line["reward_offer"] is offer
            for line in enriched
        )
    ]

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

            # A reward candle with a free unit is that offer's line now; one
            # promotion per line, so its paid units stay full price.
            if line["variant_id"] in discounts:
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
# PRICES — THE ONE PLACE A SHOPPER'S PRICE IS DECIDED
# ======================================================
# Every price the shop shows or charges comes through price_basket: the
# order itself (build_order), the cart and checkout preview, and — via
# unit_display_prices — the catalogue card and the size picker. The
# storefront never works out a discount on its own.


@dataclass(frozen=True)
class PricedLine:
    variant_id: int
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    discount_amount: Decimal
    discount_label: str
    # Units on this line that buy-two-get-three made free. A line carries at
    # most one promotion, so line_total - discount_amount is always what the
    # line costs — the figure the cart shows and the order stores.
    free_quantity: int


@dataclass(frozen=True)
class BasketPrice:
    lines: tuple[PricedLine, ...]
    subtotal: Decimal
    discount: Decimal
    # What the items cost after discounts; shipping and tax come on top.
    items_total: Decimal
    # Every promotion that applied, joined, e.g. "Spring B2G3 + Welcome 10%".
    label: str


def price_basket(*, user, lines, offers=None, welcome_offer=_RESOLVE) -> BasketPrice:
    """Price a basket exactly as checkout will charge it.

    `lines` as for compute_line_discounts. Each line's discount is rounded
    on that line, and the basket discount is their sum, so the parts always
    add up to the whole.
    """
    discounts, label = compute_line_discounts(
        user=user, lines=lines, offers=offers, welcome_offer=welcome_offer
    )

    priced = []

    for line in lines:
        unit_price = Decimal(line["unit_price"])
        quantity = int(line["quantity"])
        found = discounts.get(line["variant_id"])

        priced.append(
            PricedLine(
                variant_id=line["variant_id"],
                unit_price=unit_price,
                quantity=quantity,
                line_total=unit_price * quantity,
                discount_amount=found.amount if found else Decimal("0.00"),
                discount_label=found.label if found else "",
                free_quantity=found.free_quantity if found else 0,
            )
        )

    subtotal = sum((p.line_total for p in priced), Decimal("0.00"))
    discount = sum((p.discount_amount for p in priced), Decimal("0.00"))

    return BasketPrice(
        lines=tuple(priced),
        subtotal=subtotal,
        discount=discount,
        items_total=subtotal - discount,
        label=label if discount > 0 else "",
    )


@dataclass(frozen=True)
class UnitPrice:
    price: Decimal
    # What one of these costs this shopper on its own. Equal to `price`
    # when nothing applies to a single unit — including buy-two-get-three,
    # which needs three in the basket.
    display_price: Decimal
    discount_label: str


def unit_display_prices(
    *, user, variants, offers=None, welcome_offer=_RESOLVE
) -> dict[int, UnitPrice]:
    """The price to show for each variant: a one-unit basket each.

    Offers and the welcome offer are looked up once for the whole batch, or
    taken from the caller when it prices several batches for one request.
    `variants` need their `candle` loaded.
    """
    if offers is None:
        offers = get_active_offers()
    if welcome_offer is _RESOLVE:
        welcome_offer = get_welcome_offer(user)

    result = {}

    for variant in variants:
        priced = price_basket(
            user=user,
            lines=[
                {
                    "variant_id": variant.id,
                    "candle": variant.candle,
                    "unit_price": variant.price,
                    "quantity": 1,
                }
            ],
            offers=offers,
            welcome_offer=welcome_offer,
        ).lines[0]

        result[variant.id] = UnitPrice(
            price=priced.unit_price,
            display_price=priced.line_total - priced.discount_amount,
            discount_label=priced.discount_label,
        )

    return result


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