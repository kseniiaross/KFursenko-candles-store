from django.urls import path

from .views import PurchaseLabelAPIView, ShippingRatesAPIView

urlpatterns = [
    path("rates/", ShippingRatesAPIView.as_view(), name="shipping-rates"),
    path(
        "orders/<int:pk>/label/",
        PurchaseLabelAPIView.as_view(),
        name="shipping-purchase-label",
    ),
]
