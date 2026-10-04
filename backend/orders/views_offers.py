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
                        get_welcome_offer, unit_display_prices)

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
        "`needed` is how many more qualifying candles complete the next "
        "trio. `suggestions` lists up to six candles that would count: the "
        "basket's own qualifying variants first (most-held first, when "
        "there is stock for one more), then every other eligible candle."
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

        variants = (
            CandleVariant.objects.filter(id__in=quantities)
            .select_related("candle", "candle__category")
            .prefetch_related("candle__collections", "candle__offers")
        )

        offers = get_active_offers()

        # offer pk -> {"offer": Offer, "count": int, "in_basket": [(variant, qty)]}
        buckets: dict[int, dict] = {}

        for variant in variants:
            offer = campaign_offer_for(variant.candle, offers)

            if not offer or offer.kind != offer.Kind.B1G2:
                continue

            bucket = buckets.setdefault(
                offer.pk, {"offer": offer, "count": 0, "in_basket": []}
            )

            bucket["count"] += quantities[variant.id]
            bucket["in_basket"].append((variant, quantities[variant.id]))

        promotions = []
        welcome = None
        welcome_loaded = False

        for bucket in buckets.values():
            offer = bucket["offer"]
            count = bucket["count"]
            remainder = count % 3

            # Zero means every qualifying candle is already inside a
            # complete trio — there is nothing to nudge about.
            if remainder == 0:
                continue

            suggested = self._suggestions(offer, offers, bucket["in_basket"])

            if not welcome_loaded:
                welcome = get_welcome_offer(request.user)
                welcome_loaded = True

            units = unit_display_prices(
                user=request.user,
                variants=suggested,
                offers=offers,
                welcome_offer=welcome,
            )

            promotions.append(
                {
                    "offer_slug": offer.slug,
                    "offer_title": offer.title,
                    "badge_text": offer.badge_text,
                    "in_cart": count,
                    "needed": 3 - remainder,
                    "free_so_far": count // 3,
                    "suggestions": [
                        _serialize_suggestion(variant, units[variant.id])
                        for variant in suggested
                    ],
                }
            )

        return Response({"promotions": promotions}, status=status.HTTP_200_OK)

    def _suggestions(self, offer, offers, in_basket):
        """Candles that would count towards this offer's next trio.

        Candles already in the basket come first — another of the same scent
        is the likeliest third pick — as the exact variant the basket holds,
        so picking one raises that line's quantity rather than adding a
        second line in a different size. Most-held first. They are left out
        when there is no stock for one more.

        Then every other eligible candle, one variant each. The basket's
        candles aren't repeated there. Returns variants; the caller prices
        them in one batch.
        """
        picked = []

        for variant, quantity in sorted(
            in_basket, key=lambda pair: (-pair[1], pair[0].candle.name)
        ):
            if (
                variant.is_active
                and not variant.candle.is_sold_out
                and variant.stock_qty > quantity
            ):
                picked.append(variant)

        if len(picked) >= MAX_SUGGESTIONS:
            return picked[:MAX_SUGGESTIONS]

        basket_candle_ids = {variant.candle_id for variant, _ in in_basket}

        candidates = (
            Candle.objects.exclude(id__in=basket_candle_ids)
            .filter(is_sold_out=False)
            .select_related("category")
            .prefetch_related("collections", "offers", "variants")
            .order_by("-is_bestseller", "name")
        )

        for candle in candidates:
            if campaign_offer_for(candle, offers) is not offer:
                continue

            variant = next(
                (
                    v
                    for v in candle.variants.all()
                    if v.is_active and v.stock_qty > 0
                ),
                None,
            )

            if not variant:
                continue

            picked.append(variant)

            if len(picked) >= MAX_SUGGESTIONS:
                break

        return picked
