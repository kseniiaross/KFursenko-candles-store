from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from cart.models import Cart, CartItem

from .models import Order
from .serializers import (OrderCreateSerializer, OrderFromCartSerializer,
                          OrderReadSerializer, OrderStatusUpdateSerializer,
                          build_order)


class OrderCreateThrottle(UserRateThrottle):
    scope = "orders_create"


@extend_schema(
    tags=["Orders"],
    summary="Create order from provided items",
    description=(
        "Creates an order from request payload items.\n\n"
        "Body example:\n"
        '{ "items": [{"variant_id": 12, "quantity": 2}], "shipping": {...}, '
        '"shipping_rate_id": "rate_abc" }\n\n'
        "shipping_rate_id comes from POST /api/shipping/rates/. It is "
        "optional: without it the cheapest live rate is used, and if the "
        "carrier API is unreachable the flat fallback rate applies."
    ),
    request=OrderCreateSerializer,
    responses={201: OrderReadSerializer},
)
class CreateOrderAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderCreateSerializer
    throttle_classes = [OrderCreateThrottle]

    def post(self, request, *args, **kwargs):
        items = request.data.get("items", [])
        if not items:
            raise ValidationError({"items": "Order must contain at least one item."})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        return Response(OrderReadSerializer(order).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Orders"],
    summary="List my orders",
    description="Returns orders for the authenticated user only (latest first).",
    responses={200: OrderReadSerializer(many=True)},
)
class MyOrdersAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderReadSerializer

    def get_queryset(self):
        # select_related("shipment") matters: the serializer reads carrier
        # and tracking off it, so without this the list costs one extra
        # query per order.
        return (
            Order.objects.filter(user=self.request.user)
            .select_related("shipment")
            .prefetch_related("items__candle")
            .order_by("-created_at")
        )


@extend_schema(
    tags=["Orders"],
    summary="Staff: list all orders",
    description="Staff-only endpoint. Returns all orders in the system (latest first).",
    parameters=[
        OpenApiParameter(
            name="search",
            description=(
                "Search by order id, user email, or Stripe payment intent id "
                "(if search backend enabled)."
            ),
            required=False,
            type=str,
        ),
        OpenApiParameter(
            name="ordering",
            description=(
                "Ordering fields: created_at, total_amount, status "
                "(if ordering backend enabled). Example: -created_at"
            ),
            required=False,
            type=str,
        ),
    ],
    responses={200: OrderReadSerializer(many=True)},
)
class StaffOrdersAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderReadSerializer
    search_fields = ("id", "user__email", "stripe_payment_intent_id")
    ordering_fields = ("created_at", "total_amount", "status")
    ordering = ("-created_at",)

    def get_queryset(self):
        if not self.request.user.is_staff:
            raise PermissionDenied("Only staff can view all orders.")

        return (
            Order.objects.select_related("user", "shipment")
            .prefetch_related("items__candle")
            .order_by("-created_at")
        )


@extend_schema(
    tags=["Orders"],
    summary="Create order from server cart",
    description=(
        "Creates an order from the authenticated user's server-side cart "
        "and clears the cart after success."
    ),
    request=OrderFromCartSerializer,
    responses={201: OrderReadSerializer},
)
class CreateOrderFromCartAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderFromCartSerializer
    throttle_classes = [OrderCreateThrottle]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        user = request.user

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart, _ = Cart.objects.get_or_create(user=user)
        cart_items = list(
            CartItem.objects.select_related("variant").filter(cart=cart)
        )

        if not cart_items:
            raise ValidationError({"cart": "Cart is empty."})

        # Same assembly path as the explicit-items endpoint, so shipping,
        # stock checks and the welcome discount cannot diverge.
        order = build_order(
            user=user,
            lines=[
                {
                    "variant_id": item.variant_id,
                    "quantity": item.quantity,
                    "is_gift": item.is_gift,
                }
                for item in cart_items
            ],
            shipping=serializer.validated_data["shipping"],
            shipping_rate_id=serializer.validated_data.get("shipping_rate_id") or None,
        )

        CartItem.objects.filter(cart=cart).delete()

        return Response(OrderReadSerializer(order).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Orders"],
    summary="Get my order by id",
    description="Returns a single order for the authenticated user (only their own).",
    responses={200: OrderReadSerializer},
)
class OrderDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderReadSerializer

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .select_related("shipment")
            .prefetch_related("items__candle")
        )


@extend_schema(
    tags=["Orders"],
    summary="Staff: update order status",
    description=(
        "Staff-only. Updates order status using transition rules.\n\n"
        'Body: {"status": "shipped"}\n\n'
        "Note this only moves the status. To buy a label, use "
        "POST /api/shipping/orders/{id}/label/, which moves the order to "
        "shipped by itself once the label exists."
    ),
    request=OrderStatusUpdateSerializer,
    responses={200: OrderReadSerializer},
)
class OrderStatusUpdateAPIView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderStatusUpdateSerializer

    def patch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can update order status.")

        order_id = kwargs.get("pk")

        try:
            order = Order.objects.select_related("shipment").get(pk=order_id)
        except Order.DoesNotExist:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        try:
            order.transition_to(new_status)
        except ValueError as error:
            raise ValidationError({"status": str(error)})

        return Response(OrderReadSerializer(order).data, status=status.HTTP_200_OK)