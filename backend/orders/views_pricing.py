"""Price a basket for display, exactly as checkout will charge it.

The cart page and the checkout summary show these numbers instead of
multiplying prices in the browser. Behind it is price_basket, the function
build_order charges with, so the preview and the order cannot disagree.
"""

from collections import defaultdict

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from candles.models import CandleVariant

from .discounts import price_basket


class PricePreviewLineSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=999)


class PricePreviewRequestSerializer(serializers.Serializer):
    items = PricePreviewLineSerializer(many=True)


def _money(value) -> str:
    return str(value)


@extend_schema(
    tags=["Orders"],
    summary="Price a basket as checkout will",
    description=(
        "Given the basket's variant ids and quantities, returns each line's "
        "unit price, discount and label, and the basket's subtotal, "
        "discount and items total — the same figures build_order will "
        "charge. Shipping and tax are not included.\n\n"
        'Body: {"items": [{"variant_id": 12, "quantity": 2}]}\n\n'
        "Repeated variant ids are merged. Variants that no longer exist or "
        "are switched off are listed under `unavailable` and not priced: "
        "checkout would refuse them. Guests get no welcome offer, as at "
        "checkout."
    ),
    request=PricePreviewRequestSerializer,
)
class PricePreviewAPIView(APIView):
    # Guests have baskets too; their prices just never include the welcome
    # offer, because checkout requires an account.
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def post(self, request):
        serializer = PricePreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Merged the way build_order merges, so the same basket prices the
        # same way here and there.
        quantities: dict[int, int] = defaultdict(int)
        for line in serializer.validated_data["items"]:
            quantities[line["variant_id"]] += line["quantity"]

        variants = {
            v.id: v
            for v in CandleVariant.objects.filter(id__in=quantities).select_related(
                "candle", "candle__category"
            )
        }

        unavailable = sorted(
            vid
            for vid in quantities
            if vid not in variants or not variants[vid].is_active
        )

        priced = price_basket(
            user=request.user,
            lines=[
                {
                    "variant_id": vid,
                    "candle": variants[vid].candle,
                    "unit_price": variants[vid].price,
                    "quantity": qty,
                }
                for vid, qty in quantities.items()
                if vid not in unavailable
            ],
        )

        return Response(
            {
                "lines": [
                    {
                        "variant_id": line.variant_id,
                        "unit_price": _money(line.unit_price),
                        "quantity": line.quantity,
                        "line_total": _money(line.line_total),
                        "discount_amount": _money(line.discount_amount),
                        "discount_label": line.discount_label,
                        "line_total_after_discount": _money(
                            line.line_total - line.discount_amount
                        ),
                    }
                    for line in priced.lines
                ],
                "subtotal": _money(priced.subtotal),
                "discount": _money(priced.discount),
                "items_total": _money(priced.items_total),
                "label": priced.label,
                "unavailable": unavailable,
            },
            status=status.HTTP_200_OK,
        )
