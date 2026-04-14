from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from django.db import transaction

from .models import Cart, CartItem
from .serializers import CartSerializer, CartItemSerializer, MergeCartSerializer

from candles.models import Candle


def _get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return (
        Cart.objects
        .prefetch_related("items__candle")
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

    def create(self, request, *args, **kwargs):
        cart = _get_or_create_cart(request.user)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        candle = serializer.validated_data["candle"]
        qty = serializer.validated_data.get("quantity", 1)
        if qty <= 0:
            raise ValidationError({"quantity": "Quantity must be >= 1."})

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            candle=candle,
            defaults={"quantity": qty},
        )
        if not created:
            item.quantity += qty
            item.save(update_fields=["quantity"])

        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)


class UpdateCartItemAPIView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CartItemSerializer

    def patch(self, request, *args, **kwargs):
        cart = _get_or_create_cart(request.user)
        item_id = kwargs.get("item_id")

        try:
            item = CartItem.objects.get(id=item_id, cart=cart)
        except CartItem.DoesNotExist:
            return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)

        qty = request.data.get("quantity")
        if qty is None:
            raise ValidationError({"quantity": "This field is required."})

        try:
            qty = int(qty)
        except ValueError:
            raise ValidationError({"quantity": "Quantity must be an integer."})

        if qty <= 0:
            item.delete()
            return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

        item.quantity = qty
        item.save(update_fields=["quantity"])
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class RemoveCartItemAPIView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        cart = _get_or_create_cart(request.user)
        item_id = kwargs.get("item_id")

        CartItem.objects.filter(id=item_id, cart=cart).delete()
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

class MergeCartAPIView(generics.GenericAPIView):
    """
    POST /api/cart/merge/
    Body:
    {
      "items": [
        {"candle_id": 12, "quantity": 2},
        {"candle_id": 5, "quantity": 1}
      ]
    }

    Merges guest cart into server cart for authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MergeCartSerializer

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        cart = _get_or_create_cart(request.user)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data["items"]

        # 1) Sum duplicates in payload
        merged = {}
        for i in items:
            cid = int(i["candle_id"])
            qty = int(i["quantity"])
            merged[cid] = merged.get(cid, 0) + qty

        candle_ids = list(merged.keys())

        # 2) Fetch candles (and lock if you later add stock_qty)
        candles = Candle.objects.select_for_update().filter(id__in=candle_ids)
        candle_map = {c.id: c for c in candles}

        if len(candle_map) != len(candle_ids):
            missing = sorted(set(candle_ids) - set(candle_map.keys()))
            raise ValidationError({"items": f"Some candle_id do not exist: {missing}"})

        # 3) Apply merge
        for cid, qty in merged.items():
            candle = candle_map[cid]

            # minimal availability check
            if not candle.in_stock:
                # For Oscar: we skip out-of-stock, or raise — choose one behavior.
                # I suggest: raise error to be strict and predictable.
                raise ValidationError({"items": f"Item is out of stock: {candle.name} (id={cid})"})

            item, created = CartItem.objects.get_or_create(
                cart=cart,
                candle=candle,
                defaults={"quantity": qty},
            )
            if not created:
                item.quantity += qty
                item.save(update_fields=["quantity"])

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)