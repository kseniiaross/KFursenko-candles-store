from collections import defaultdict

from rest_framework import serializers

from orders.serializers import OrderItemCreateSerializer, ShippingSerializer

from .models import Shipment

# The most of one candle an order can hold, so the most worth quoting.
# Uncapped, build_parcels made one parcel per box: 10**9 units was ~140
# million dicts and an out-of-memory kill.
MAX_UNITS_PER_CANDLE = OrderItemCreateSerializer().fields["quantity"].max_value


class RateQuoteItemSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_UNITS_PER_CANDLE)


class RateQuoteAddressSerializer(ShippingSerializer):
    """The order's address rules, except the name: checkout asks for rates
    as soon as the address is complete, before a name has been typed."""

    full_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class RateQuoteRequestSerializer(serializers.Serializer):
    """Quote for a cart that has not become an order yet."""

    shipping = RateQuoteAddressSerializer()
    items = RateQuoteItemSerializer(many=True, required=False)

    def validate_items(self, items):
        """One line per candle. Lines for the same candle are added up, as an
        order does, and the total is held to the same cap — otherwise two
        lines of 999 would get round it."""
        totals: dict[int, int] = defaultdict(int)

        for item in items:
            totals[item["variant_id"]] += item["quantity"]

        if any(quantity > MAX_UNITS_PER_CANDLE for quantity in totals.values()):
            raise serializers.ValidationError(
                f"At most {MAX_UNITS_PER_CANDLE} of one candle can be quoted."
            )

        return [
            {"variant_id": variant_id, "quantity": quantity}
            for variant_id, quantity in totals.items()
        ]


class RateSerializer(serializers.Serializer):
    rate_id = serializers.CharField()
    carrier = serializers.CharField()
    service_level = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    estimated_days = serializers.IntegerField(allow_null=True, required=False)
    duration_terms = serializers.CharField(allow_blank=True, required=False)


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = (
            "id",
            "status",
            "carrier",
            "service_level",
            "amount",
            "currency",
            "tracking_number",
            "tracking_url",
            "label_url",
            "is_test",
            "error_message",
            "created_at",
        )
