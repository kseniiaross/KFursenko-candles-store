from rest_framework import serializers

from candles.models import Candle
from .models import Cart, CartItem


def build_cloudinary_url(file_field):
    if not file_field:
        return None

    try:
        return file_field.build_url(secure=True)
    except Exception:
        return str(file_field)


class CartItemSerializer(serializers.ModelSerializer):
    candle_id = serializers.PrimaryKeyRelatedField(
        queryset=Candle.objects.all(),
        source="candle",
        write_only=True,
    )

    candle = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CartItem
        fields = ("id", "candle", "candle_id", "quantity")
        read_only_fields = ("id", "candle")

    def get_candle(self, obj):
        return {
            "id": obj.candle_id,
            "name": obj.candle.name,
            "price": str(obj.candle.price),
            "slug": obj.candle.slug,
            "image": build_cloudinary_url(obj.candle.image),
            "in_stock": obj.candle.in_stock,
        }

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be >= 1.")
        return value


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ("id", "items", "created_at", "updated_at")
        read_only_fields = ("id", "items", "created_at", "updated_at")


class MergeCartItemInputSerializer(serializers.Serializer):
    candle_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=999)


class MergeCartSerializer(serializers.Serializer):
    items = MergeCartItemInputSerializer(many=True)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("items must not be empty.")
        return items