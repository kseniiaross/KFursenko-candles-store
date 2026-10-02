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

from .discounts import campaign_offer_for, get_active_offers

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


def _serialize_suggestion(variant) -> dict:
    candle = variant.candle

    return {
        "candle_id": candle.id,
        "variant_id": variant.id,
        "name": candle.name,
        "slug": candle.slug,
        "size": variant.size,
        "price": str(variant.price),
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
        "trio. `suggestions` lists candles that would count, excluding "
        "what is already in the cart."
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

        # offer pk -> {"offer": Offer, "count": int, "candle_ids": set}
        buckets: dict[int, dict] = {}

        for variant in variants:
            offer = campaign_offer_for(variant.candle, offers)

            if not offer or offer.kind != offer.Kind.B1G2:
                continue

            bucket = buckets.setdefault(
                offer.pk, {"offer": offer, "count": 0, "candle_ids": set()}
            )

            bucket["count"] += quantities[variant.id]
            bucket["candle_ids"].add(variant.candle_id)

        promotions = []

        for bucket in buckets.values():
            offer = bucket["offer"]
            count = bucket["count"]
            remainder = count % 3

            # Zero means every qualifying candle is already inside a
            # complete trio — there is nothing to nudge about.
            if remainder == 0:
                continue

            promotions.append(
                {
                    "offer_slug": offer.slug,
                    "offer_title": offer.title,
                    "badge_text": offer.badge_text,
                    "in_cart": count,
                    "needed": 3 - remainder,
                    "free_so_far": count // 3,
                    "suggestions": self._suggestions(
                        offer, offers, bucket["candle_ids"]
                    ),
                }
            )

        return Response({"promotions": promotions}, status=status.HTTP_200_OK)

    def _suggestions(self, offer, offers, exclude_candle_ids):
        """Candles that would count towards this offer's next trio.

        Candles already in the cart are left out: the shopper can raise
        their quantity from the cart itself, and repeating them here
        makes the prompt look like it did not read the basket.
        """
        candidates = (
            Candle.objects.exclude(id__in=exclude_candle_ids)
            .filter(is_sold_out=False)
            .select_related("category")
            .prefetch_related("collections", "offers", "variants")
            .order_by("-is_bestseller", "name")
        )

        picked = []

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

            picked.append(_serialize_suggestion(variant))

            if len(picked) >= MAX_SUGGESTIONS:
                break

        return picked