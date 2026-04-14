from django.urls import path
from .views import SubscribeAPIView

urlpatterns = [
    path("subscribe/", SubscribeAPIView.as_view(), name="newsletter-subscribe"),
]