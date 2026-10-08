"""Tells the storefront how close a basket is to earning a free candle.

Eligibility lives in the Offer tables — category, collection and direct
links — none of which the cart carries. A cart line knows a variant id, a
price and a picture, so the question "does this qualify?" can only be
answered here.
"""

from candles.models import Candle, CandleVariant
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from .discounts import (campaign_offer_for, get_active_offers,
                        get_welcome_offer, has_reward_group, offer_rewards,
                        offer_standing, price_basket, reward_offer_for,
                        unit_display_prices)

# How many alternatives to offer in the prompt. More than a handful turns a
# nudge into a second catalogue page.
MAX_SUGGESTIONS = 6


class OfferProgressLineSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=999)


class OfferProgressRequestSerializer(serializers.Serializer):
    items = OfferProgressLineSerializer(many=True)


def _image_url(candle) -> str:
    """CloudinaryField raises rather than returning None when empty."""
    try:
        return candle.image.url if candle.image else ""
    except (AttributeError, ValueError):
        return ""


def _serialize_suggestion(variant, unit) -> dict:
    candle = variant.candle

    return {
        "candle_id": candle.id,
        "variant_id": variant.id,
        "name": candle.name,
        "slug": candle.slug,
        "size": variant.size,
        "price": str(variant.price),
        # What one costs this shopper, from the function checkout charges
        # with. For a buy-two-get-three candle that is always `price` — one
        # unit earns nothing — but the prompt shouldn't rely on knowing that.
        "display_price": str(unit.display_price),
        "image": _image_url(candle),
    }


@extend_schema(
    tags=["Offers"],
    summary="How close the basket is to a free candle",
    description=(
        "Given the cart's variant ids and quantities, reports every "
        "buy-two-get-three offer the basket has partly earned.\n\n"
        'Body: {"items": [{"variant_id": 12, "quantity": 2}]}\n\n'
        "`needed` is how many more candles earn the next free one. "
        "`suggestions` lists up to six candles that can be the free one: the "
        "basket's own variants first (most-held first, when there is stock "
        "for one more), then every other. When `needed` is 1, only candles "
        "that would actually come out free are listed. `reward_group` is "
        "true when the offer's free candle comes from its own group rather "
        "than from the candles that qualify. `replaces_label` names the "
        "welcome offer the basket would lose on the candles that pay for the "
        "free one, when it would; empty otherwise."
    ),
    request=OfferProgressRequestSerializer,
)
class OfferProgressAPIView(APIView):
    # Guests build carts too, and the prompt is the same for them.
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def post(self, request):
        serializer = OfferProgressRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lines = serializer.validated_data["items"]

        if not lines:
            return Response({"promotions": []}, status=status.HTTP_200_OK)

        quantities = {line["variant_id"]: line["quantity"] for line in lines}

        variants = list(
            CandleVariant.objects.filter(id__in=quantities)
            .select_related("candle", "candle__category")
            .prefetch_related("candle__collections", "candle__offers")
        )

        offers = get_active_offers()

        basket = [
            {
                "variant_id": variant.id,
                "candle": variant.candle,
                "unit_price": variant.price,
                "quantity": quantities[variant.id],
            }
            for variant in variants
        ]

        # Offers this basket touches, in priority order, with the basket
        # variants that can be the free one.
        touched: dict[int, dict] = {}

        for variant in variants:
            campaign = campaign_offer_for(variant.candle, offers)

            if campaign is not None and campaign.kind == campaign.Kind.B1G2:
                offer = campaign
                rewards = offer_rewards(offer, variant.candle)
            elif campaign is None:
                offer = reward_offer_for(variant.candle, offers)
                rewards = offer is not None
            else:
                continue

            if offer is None:
                continue

            bucket = touched.setdefault(offer.pk, {"offer": offer, "rewards": []})

            if rewards:
                bucket["rewards"].append((variant, quantities[variant.id]))

        promotions = []
        welcome = None
        welcome_loaded = False

        for offer in offers:
            if offer.pk not in touched:
                continue

            standing = offer_standing(offer=offer, lines=basket, offers=offers)

            # Every unit is already matched into a free candle and its two
            # payers: there is nothing to nudge about.
            if standing.in_offer - 3 * standing.free <= 0:
                continue

            needed = self._needed(offer, standing)

            suggested = self._suggestions(
                offer,
                offers,
                touched[offer.pk]["rewards"],
                basket,
                standing.free if needed == 1 else None,
            )

            if not welcome_loaded:
                welcome = get_welcome_offer(request.user)
                welcome_loaded = True

            units = unit_display_prices(
                user=request.user,
                variants=suggested,
                offers=offers,
                welcome_offer=welcome,
            )

            replaces = ""

            if needed == 1 and suggested:
                replaces = self._replaces(
                    request.user, basket, suggested[0], offers, welcome
                )

            promotions.append(
                {
                    "offer_slug": offer.slug,
                    "offer_title": offer.title,
                    "badge_text": offer.badge_text,
                    "reward_group": has_reward_group(offer),
                    "in_cart": standing.in_offer,
                    "needed": needed,
                    "free_so_far": standing.free,
                    "replaces_label": replaces,
                    "suggestions": [
                        _serialize_suggestion(variant, units[variant.id])
                        for variant in suggested
                    ],
                }
            )

        return Response({"promotions": promotions}, status=status.HTTP_200_OK)

    @staticmethod
    def _replaces(user, basket, variant, offers, welcome):
        """The welcome offer the basket loses if the shopper takes this free
        candle, or "". Priced both ways by the function checkout uses: a
        line that has the welcome discount now and none after is a line
        that would pay for the free candle."""
        if welcome is None:
            return ""

        held = next((line for line in basket if line["variant_id"] == variant.id), None)
        after_lines = [line for line in basket if line is not held] + [
            {
                "variant_id": variant.id,
                "candle": variant.candle,
                "unit_price": variant.price,
                "quantity": (held["quantity"] if held else 0) + 1,
            }
        ]

        before = price_basket(user=user, lines=basket, offers=offers, welcome_offer=welcome)
        after = price_basket(user=user, lines=after_lines, offers=offers, welcome_offer=welcome)
        after_by_id = {line.variant_id: line for line in after.lines}

        for line in before.lines:
            if line.discount_label != welcome.title:
                continue

            later = after_by_id.get(line.variant_id)

            if later is not None and later.discount_amount == 0:
                return welcome.title

        return ""

    @staticmethod
    def _needed(offer, standing):
        """How many more candles earn the next free one.

        Without a reward group every candle can pay or be free, so it is
        whatever completes the next three. With one, the next free candle
        needs two payers and a reward candle of its own; this counts what is
        missing of each, assuming the candles added are priced to fit.
        """
        if not has_reward_group(offer):
            return 3 - standing.in_offer % 3

        target = standing.free + 1
        payers_short = max(0, 2 * target - standing.can_pay)
        rewards_short = max(0, target - standing.can_be_free)

        # A candle in both groups can't be payer and free candle at once.
        return max(1, payers_short + rewards_short, 3 * target - standing.in_offer)

    def _suggestions(self, offer, offers, in_basket, basket, free_now):
        """Candles that can be this offer's free one.

        Candles already in the basket come first — another of the same scent
        is the likeliest third pick — as the exact variant the basket holds,
        so picking one raises that line's quantity rather than adding a
        second line in a different size. Most-held first. They are left out
        when there is no stock for one more.

        Then every other candle that can be the free one, one variant each.
        The basket's candles aren't repeated there.

        `free_now` is the basket's free count when one candle should earn
        the next free one; then a candle is only listed if adding it really
        does, so the prompt never offers a free candle that would be charged
        (one dearer than the two it comes with, say). Returns variants; the
        caller prices them in one batch.
        """
        picked = []

        def earns(variant):
            if free_now is None:
                return True

            held = next(
                (line for line in basket if line["variant_id"] == variant.id), None
            )
            added = [line for line in basket if line is not held] + [
                {
                    "variant_id": variant.id,
                    "candle": variant.candle,
                    "unit_price": variant.price,
                    "quantity": (held["quantity"] if held else 0) + 1,
                }
            ]

            return (
                offer_standing(offer=offer, lines=added, offers=offers).free
                > free_now
            )

        for variant, quantity in sorted(
            in_basket, key=lambda pair: (-pair[1], pair[0].candle.name)
        ):
            if (
                variant.is_active
                and not variant.candle.is_sold_out
                and variant.stock_qty > quantity
                and earns(variant)
            ):
                picked.append(variant)

        if len(picked) >= MAX_SUGGESTIONS:
            return picked[:MAX_SUGGESTIONS]

        basket_candle_ids = {variant.candle_id for variant, _ in in_basket}
        basket_candle_ids |= {line["candle"].id for line in basket}

        candidates = (
            Candle.objects.exclude(id__in=basket_candle_ids)
            .filter(is_sold_out=False)
            .select_related("category")
            .prefetch_related("collections", "offers", "variants")
            .order_by("-is_bestseller", "name")
        )

        for candle in candidates:
            campaign = campaign_offer_for(candle, offers)

            if campaign is offer:
                if not offer_rewards(offer, candle):
                    continue
            elif campaign is not None or reward_offer_for(candle, offers) is not offer:
                continue

            variant = next(
                (
                    v
                    for v in candle.variants.all()
                    if v.is_active and v.stock_qty > 0
                ),
                None,
            )

            if not variant or not earns(variant):
                continue

            picked.append(variant)

            if len(picked) >= MAX_SUGGESTIONS:
                break

        return picked
