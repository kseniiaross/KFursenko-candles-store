from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from rest_framework import serializers

from candles.models import CandleVariant
from shipping.normalize import payload_to_address
from shipping.services import resolve_shipping_cost

from .discounts import get_welcome_offer, welcome_percent_for
from .models import Order, OrderItem


class OrderItemReadSerializer(serializers.ModelSerializer):
    candle_id = serializers.IntegerField(source="candle.id", read_only=True)
    candle_name = serializers.CharField(source="candle.name", read_only=True)

    price = serializers.DecimalField(
        source="unit_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "candle_id",
            "candle_name",
            "product_name",
            "price",
            "unit_price",
            "quantity",
            "line_total",
            "is_gift",
        )

    def get_line_total(self, obj):
        return obj.line_total()


class OrderReadSerializer(serializers.ModelSerializer):
    items = OrderItemReadSerializer(many=True, read_only=True)

    # Shipment is a OneToOne that may not exist yet — a label is only bought
    # after payment. Touching a missing reverse OneToOne raises rather than
    # returning None, hence getattr with a default in every accessor below.
    carrier = serializers.SerializerMethodField()
    service_level = serializers.SerializerMethodField()
    tracking_number = serializers.SerializerMethodField()
    tracking_url = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "status",
            "currency",
            "subtotal_amount",
            "discount_amount",
            "discount_label",
            "shipping_amount",
            "tax_amount",
            "total_amount",
            "shipping_full_name",
            "shipping_line1",
            "shipping_line2",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
            "shipping_phone",
            "carrier",
            "service_level",
            "tracking_number",
            "tracking_url",
            "stripe_payment_intent_id",
            "stripe_tax_calculation_id",
            "items",
            "created_at",
        )

    def _shipment(self, obj):
        return getattr(obj, "shipment", None)

    def get_carrier(self, obj):
        shipment = self._shipment(obj)
        return shipment.carrier if shipment else ""

    def get_service_level(self, obj):
        shipment = self._shipment(obj)
        return shipment.service_level if shipment else ""

    def get_tracking_number(self, obj):
        shipment = self._shipment(obj)
        return shipment.tracking_number if shipment else ""

    def get_tracking_url(self, obj):
        shipment = self._shipment(obj)
        return shipment.tracking_url if shipment else ""


class OrderItemCreateSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=999)
    is_gift = serializers.BooleanField(required=False, default=False)

    def validate_variant_id(self, value):
        if value <= 0:
            raise serializers.ValidationError("Please select a valid candle option.")
        return value


class ShippingSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    line1 = serializers.CharField(max_length=255)
    line2 = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
    city = serializers.CharField(max_length=255)
    state = serializers.CharField(max_length=255)
    postal_code = serializers.CharField(max_length=32)

    country = serializers.CharField(
        max_length=120,
        default="United States",
    )

    phone = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_country(self, value: str) -> str:
        country = (value or "").strip()

        if not country:
            raise serializers.ValidationError("Please enter your country.")

        return country


# ======================================================
# ORDER ASSEMBLY
# ======================================================
@transaction.atomic
def build_order(*, user, lines, shipping, shipping_rate_id=None):
    """The single place an order is assembled.

    Both entry points — an explicit item list and the server-side cart —
    run through here, so stock checks, the shipping cost and the welcome
    discount cannot drift apart between them.
    """
    merged: dict[int, dict[str, int | bool]] = {}

    for line in lines:
        variant_id = int(line["variant_id"])
        qty = int(line["quantity"])
        is_gift = bool(line.get("is_gift", False))

        if variant_id not in merged:
            merged[variant_id] = {"quantity": 0, "is_gift": False}

        merged[variant_id]["quantity"] = int(merged[variant_id]["quantity"]) + qty
        merged[variant_id]["is_gift"] = bool(merged[variant_id]["is_gift"]) or is_gift

    variant_ids = list(merged.keys())

    variants = (
        CandleVariant.objects.select_for_update()
        .select_related("candle", "candle__category")
        .filter(id__in=variant_ids)
    )

    variant_map = {variant.id: variant for variant in variants}

    if len(variant_map) != len(variant_ids):
        raise serializers.ValidationError(
            {"items": "Some items in your cart are no longer available."}
        )

    # Availability is checked before anything slow happens. Quoting first
    # would mean a live call to a carrier API for a cart that cannot be
    # fulfilled anyway — and would hold the select_for_update lock on these
    # rows for the two or three seconds that call takes.
    for variant_id, payload in merged.items():
        variant = variant_map[variant_id]
        qty = int(payload["quantity"])

        if not variant.is_active:
            raise serializers.ValidationError(
                {
                    "items": (
                        f"{variant.candle.name} / {variant.size} is currently "
                        "unavailable."
                    )
                }
            )

        if variant.stock_qty < qty:
            raise serializers.ValidationError(
                {
                    "items": (
                        f"Only {variant.stock_qty} left for "
                        f"{variant.candle.name} / {variant.size}."
                    )
                }
            )

    quote_lines = [
        (variant_map[vid], int(payload["quantity"]))
        for vid, payload in merged.items()
    ]

    shipping_amount, rate = resolve_shipping_cost(
        address_to=payload_to_address(shipping),
        lines=quote_lines,
        rate_id=shipping_rate_id,
    )

    # Resolved before the order row exists, so the order being created
    # cannot disqualify its own discount.
    welcome_offer = get_welcome_offer(user)

    order = Order.objects.create(
        user=user,
        status=Order.Status.PENDING,
        currency="usd",
        subtotal_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        shipping_amount=shipping_amount,
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
        shipping_full_name=shipping["full_name"].strip(),
        shipping_line1=shipping["line1"].strip(),
        shipping_line2=(shipping.get("line2") or "").strip(),
        shipping_city=shipping["city"].strip(),
        shipping_state=shipping["state"].strip(),
        shipping_postal_code=shipping["postal_code"].strip(),
        shipping_country=shipping["country"].strip(),
        shipping_phone=(shipping.get("phone") or "").strip(),
    )

    if rate:
        from shipping.models import Shipment

        Shipment.objects.create(
            order=order,
            rate_id=rate["rate_id"],
            carrier=rate["carrier"],
            service_level=rate["service_level"],
            amount=rate["amount"],
            currency=rate["currency"].lower(),
        )

    subtotal = Decimal("0.00")
    discount = Decimal("0.00")

    for variant_id, payload in merged.items():
        variant = variant_map[variant_id]
        candle = variant.candle
        qty = int(payload["quantity"])
        is_gift = bool(payload["is_gift"])

        variant.stock_qty -= qty
        variant.save(update_fields=["stock_qty"])

        OrderItem.objects.create(
            order=order,
            candle=candle,
            variant=variant,
            product_name=f"{candle.name} - {variant.size}",
            unit_price=variant.price,
            quantity=qty,
            is_gift=is_gift,
        )

        line_total = variant.price * qty
        subtotal += line_total

        percent = welcome_percent_for(candle, welcome_offer)

        if percent:
            discount += line_total * percent / Decimal("100")

    discount = discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    order.subtotal_amount = subtotal
    order.discount_amount = discount
    order.discount_label = welcome_offer.title if discount > 0 else ""
    order.total_amount = subtotal - discount + order.shipping_amount + order.tax_amount
    order.save(
        update_fields=[
            "subtotal_amount",
            "discount_amount",
            "discount_label",
            "total_amount",
        ]
    )

    return order


class OrderCreateSerializer(serializers.Serializer):
    items = OrderItemCreateSerializer(many=True)
    shipping = ShippingSerializer()
    shipping_rate_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    def create(self, validated_data):
        return build_order(
            user=self.context["request"].user,
            lines=validated_data["items"],
            shipping=validated_data["shipping"],
            shipping_rate_id=validated_data.get("shipping_rate_id") or None,
        )


class OrderFromCartSerializer(serializers.Serializer):
    """Shipping for a cart-based order.

    This endpoint used to take no shipping at all and skipped the flat
    rate entirely, producing orders that could not be fulfilled or
    charged correctly.
    """

    shipping = ShippingSerializer()
    shipping_rate_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)

    def validate_status(self, value: str) -> str:
        return value