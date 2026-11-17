from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (CustomTokenObtainPairView, ProfileAPIView, RegisterAPIView,
                    TermsAPIView)

urlpatterns = [
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("terms/", TermsAPIView.as_view(), name="terms"),
    path("login/", CustomTokenObtainPairView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("profile/", ProfileAPIView.as_view(), name="profile"),
]
