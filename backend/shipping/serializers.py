from rest_framework import serializers

from .models import Shipment


class RateQuoteRequestSerializer(serializers.Serializer):
    """Quote for a cart that has not become an order yet."""

    shipping = serializers.DictField()
    items = serializers.ListField(child=serializers.DictField(), required=False)


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
