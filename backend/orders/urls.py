from django.urls import path

from .views import (CancelMyOrderAPIView, CreateOrderAPIView,
                    CreateOrderFromCartAPIView, MyOrdersAPIView,
                    OrderDetailAPIView, OrderStatusUpdateAPIView,
                    StaffOrdersAPIView)
from .views_offers import OfferProgressAPIView
from .views_stripe import CreatePaymentIntentView, stripe_webhook

urlpatterns = [
    path("", CreateOrderAPIView.as_view(), name="create-order"),
    path("my/", MyOrdersAPIView.as_view(), name="orders-my"),
    path("staff/", StaffOrdersAPIView.as_view(), name="orders-staff"),

    path(
        "from-cart/",
        CreateOrderFromCartAPIView.as_view(),
        name="create-order-from-cart",
    ),
    path("<int:pk>/", OrderDetailAPIView.as_view(), name="order-detail"),
    path(
        "<int:pk>/status/",
        OrderStatusUpdateAPIView.as_view(),
        name="order-status-update",
    ),
    path(
        "<int:pk>/cancel/",
        CancelMyOrderAPIView.as_view(),
        name="order-cancel",
    ),
    path(
        "create-intent/",
        CreatePaymentIntentView.as_view(),
        name="create-payment-intent",
    ),
    path("webhook/", stripe_webhook, name="stripe-webhook"),

    # Open to guests: a basket earns the same promotion whether or not
    # someone has signed in yet.
    path(
        "offer-progress/",
        OfferProgressAPIView.as_view(),
        name="offer-progress",
    ),
]