from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from candles.models import CandleVariant

from .models import MAX_LINE_QUANTITY, Cart, CartItem
from .serializers import (CartItemSerializer, CartSerializer,
                          MergeCartSerializer, _too_many)


def _get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return (
        Cart.objects
        .prefetch_related("items__variant__candle")
        .get(pk=cart.pk)
    )


class MyCartAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CartSerializer

    def get_object(self):
        return _get_or_create_cart(self.request.user)


class AddCartItemAPIView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CartItemSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        cart = _get_or_create_cart(request.user)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        variant = CandleVariant.objects.select_for_update().get(
            pk=serializer.validated_data["variant"].pk
        )
        qty = serializer.validated_data.get("quantity", 1)
        is_gift = bool(serializer.validated_data.get("is_gift", False))

        if not variant.is_active:
            raise ValidationError({"variant_id": "This candle option is not available."})

        if variant.stock_qty < qty:
            raise ValidationError({"quantity": "Not enough stock for this candle option."})

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            variant=variant,
            defaults={"quantity": qty, "is_gift": is_gift},
        )

        if not created:
            new_qty = item.quantity + qty

            if new_qty > MAX_LINE_QUANTITY:
                raise ValidationError({"quantity": _too_many()})

            if variant.stock_qty < new_qty:
                raise ValidationError({"quantity": "Not enough stock for this candle option."})

            item.quantity = new_qty
            item.is_gift = is_gift
            item.save(update_fields=["quantity", "is_gift"])

        cart = _get_or_create_cart(request.user)
        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)


class UpdateCartItemAPIView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CartItemSerializer

    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        cart = _get_or_create_cart(request.user)
        item_id = kwargs.get("item_id")

        try:
            item = (
                CartItem.objects
                .select_related("variant", "variant__candle")
                .select_for_update()
                .get(id=item_id, cart=cart)
            )
        except CartItem.DoesNotExist:
            return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)

        qty = request.data.get("quantity", item.quantity)
        is_gift = request.data.get("is_gift", item.is_gift)

        try:
            qty = int(qty)
        except (TypeError, ValueError):
            raise ValidationError({"quantity": "Quantity must be a number."})

        if qty <= 0:
            item.delete()
            cart = _get_or_create_cart(request.user)
            return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

        if qty > MAX_LINE_QUANTITY:
            raise ValidationError({"quantity": _too_many()})

        if not item.variant.is_active:
            raise ValidationError({"variant_id": "This candle option is not available."})

        if item.variant.stock_qty < qty:
            raise ValidationError({"quantity": "Not enough stock for this candle option."})

        item.quantity = qty
        item.is_gift = bool(is_gift)
        item.save(update_fields=["quantity", "is_gift"])

        cart = _get_or_create_cart(request.user)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class RemoveCartItemAPIView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        cart = _get_or_create_cart(request.user)
        item_id = kwargs.get("item_id")

        CartItem.objects.filter(id=item_id, cart=cart).delete()

        cart = _get_or_create_cart(request.user)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


def _adjustment(variant_id, variant, reason, *, quantity=None):
    """One guest line the merge couldn't take as it was.

    reason: "unavailable" (switched off or gone), "sold_out", or "limited"
    (lowered to what's left; `quantity` is what the cart now holds). Name
    and size are empty for a candle that no longer exists; the storefront
    has them from its own copy of the line.
    """
    return {
        "variant_id": variant_id,
        "reason": reason,
        "name": variant.candle.name if variant else "",
        "size": variant.size if variant else "",
        "quantity": quantity,
    }


class MergeCartAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MergeCartSerializer

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        cart = _get_or_create_cart(request.user)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        items = serializer.validated_data["items"]

        merged: dict[int, dict[str, int | bool]] = {}

        for item in items:
            variant_id = int(item["variant_id"])
            qty = int(item["quantity"])
            is_gift = bool(item.get("is_gift", False))

            if variant_id not in merged:
                merged[variant_id] = {"quantity": 0, "is_gift": False}

            merged[variant_id]["quantity"] = int(merged[variant_id]["quantity"]) + qty
            merged[variant_id]["is_gift"] = bool(merged[variant_id]["is_gift"]) or is_gift

        variants = (
            CandleVariant.objects
            .select_for_update()
            .select_related("candle")
            .filter(id__in=merged)
        )

        variant_map = {variant.id: variant for variant in variants}
        adjustments = []

        # Whatever can be merged is; whatever can't is left out or lowered,
        # and listed in `adjustments` so the storefront can say so. Refusing
        # the lot over one sold-out candle lost the whole guest cart.
        for variant_id, payload in merged.items():
            variant = variant_map.get(variant_id)
            qty = int(payload["quantity"])
            is_gift = bool(payload["is_gift"])

            if variant is None or not variant.is_active:
                adjustments.append(_adjustment(variant_id, variant, "unavailable"))
                continue

            existing = CartItem.objects.filter(cart=cart, variant=variant).first()
            wanted = min((existing.quantity if existing else 0) + qty, MAX_LINE_QUANTITY)
            stock = max(variant.stock_qty, 0)

            # The merged line is what checkout would accept, so what the
            # storefront says about it stays true — including a line the
            # account's cart already held.
            if stock == 0:
                if existing:
                    existing.delete()
                adjustments.append(_adjustment(variant_id, variant, "sold_out"))
                continue

            final_qty = wanted

            if wanted > stock:
                final_qty = stock
                adjustments.append(
                    _adjustment(variant_id, variant, "limited", quantity=final_qty)
                )

            if existing:
                existing.quantity = final_qty
                existing.is_gift = existing.is_gift or is_gift
                existing.save(update_fields=["quantity", "is_gift"])
            else:
                CartItem.objects.create(
                    cart=cart,
                    variant=variant,
                    quantity=final_qty,
                    is_gift=is_gift,
                )

        cart = _get_or_create_cart(request.user)
        return Response(
            {**CartSerializer(cart).data, "adjustments": adjustments},
            status=status.HTTP_200_OK,
        )


class ClearCartAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        cart = _get_or_create_cart(request.user)
        CartItem.objects.filter(cart=cart).delete()

        cart = _get_or_create_cart(request.user)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)
