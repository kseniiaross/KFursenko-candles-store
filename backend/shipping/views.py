from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from cart.models import Cart, CartItem
from candles.models import CandleVariant
from orders.models import Order

from .client import ShippoError, ShippoNotConfigured
from .models import Shipment
from .normalize import AddressError, payload_to_address
from .serializers import (RateQuoteRequestSerializer, RateSerializer,
                          ShipmentSerializer)
from .services import purchase_label, quote_rates


class ShippingRatesThrottle(UserRateThrottle):
    # Every call is a POST /shipments/ upstream. Test mode allows 50/min for
    # the whole account, so a chatty checkout form will exhaust it fast.
    scope = "shipping_rates"


@extend_schema(
    tags=["Shipping"],
    summary="Quote live shipping rates",
    description=(
        "Prices the authenticated user's cart against a destination address.\n\n"
        'Body: {"shipping": {"full_name": "...", "line1": "...", "city": "...", '
        '"state": "CA", "postal_code": "94105", "country": "US"}}\n\n'
        "Returns rates cheapest-first. Pass the chosen rate_id to order "
        "creation; the server re-reads the price from Shippo before charging."
    ),
    request=RateQuoteRequestSerializer,
    responses={200: RateSerializer(many=True)},
)
class ShippingRatesAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RateQuoteRequestSerializer
    throttle_classes = [ShippingRatesThrottle]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lines = self._resolve_lines(request, serializer.validated_data)

        if not lines:
            raise ValidationError({"items": "Nothing to ship."})

        try:
            address = payload_to_address(serializer.validated_data["shipping"])
            rates = quote_rates(address_to=address, lines=lines)

        except AddressError as exc:
            # The customer can fix this one, so it is a 400 with the reason.
            raise ValidationError({"shipping": str(exc)})

        except ShippoNotConfigured:
            return Response(
                {"detail": "Live shipping rates are unavailable right now."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except ShippoError as exc:
            return Response(
                {"detail": "Could not retrieve shipping rates.", "reason": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(RateSerializer(rates, many=True).data)

    def _resolve_lines(self, request, data):
        """Explicit items when given, otherwise the server-side cart."""
        payload_items = data.get("items")

        if payload_items:
            wanted = {int(i["variant_id"]): int(i["quantity"]) for i in payload_items}
            variants = CandleVariant.objects.filter(id__in=wanted).select_related("candle")
            return [(v, wanted[v.id]) for v in variants]

        cart = Cart.objects.filter(user=request.user).first()

        if not cart:
            return []

        items = CartItem.objects.select_related("variant__candle").filter(cart=cart)

        return [(item.variant, item.quantity) for item in items]


@extend_schema(
    tags=["Shipping"],
    summary="Staff: buy the shipping label for an order",
    description=(
        "Purchases a label through Shippo. Idempotent — calling it twice on the "
        "same order returns the existing shipment rather than buying again."
    ),
    request=None,
    responses={200: ShipmentSerializer},
)
class PurchaseLabelAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ShipmentSerializer

    def post(self, request, pk, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can purchase labels.")

        try:
            order = Order.objects.select_related("user").get(pk=pk)
        except Order.DoesNotExist:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if order.status != Order.Status.PAID:
            raise ValidationError(
                {"order": f"Order must be paid before shipping (is: {order.status})."}
            )

        try:
            shipment = purchase_label(order)

        except AddressError as exc:
            raise ValidationError({"shipping": str(exc)})

        except (ShippoError, ShippoNotConfigured) as exc:
            return Response(
                {"detail": "Label purchase failed.", "reason": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if shipment.status == Shipment.Status.PURCHASED and order.can_transition(
            Order.Status.SHIPPED
        ):
            order.transition_to(Order.Status.SHIPPED)

        return Response(ShipmentSerializer(shipment).data)
