from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import TermsAcceptance
from .serializers import (CustomTokenObtainPairSerializer, ProfileSerializer,
                          RegisterSerializer)
from .terms import current_terms


class TermsAPIView(APIView):
    """The terms a new account accepts now, for Register to show. `terms` is
    null when no sign-up discount is running."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"terms": current_terms(request.query_params.get("locale"))})


class RegisterAPIView(generics.CreateAPIView):
    """Every new account accepts the sign-up discount's terms, whichever way
    the shopper came in, because every new account gets the discount.

    The page sends the version of the terms it showed. If that isn't the
    current version (the page is older than a change to the wording or the
    offer, or it never got the terms), the answer is a 409 carrying the
    current terms, for the page to show and ask again: never a dead end,
    and never a record of words the shopper wasn't shown.
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        terms = current_terms(request.data.get("locale"))
        sent = str(request.data.get("terms_version") or "")

        if terms and sent != terms["version"]:
            return Response(
                {
                    "code": "terms_outdated" if sent else "terms_required",
                    "terms": terms,
                },
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            user = serializer.save()

            if terms:
                TermsAcceptance.objects.create(user=user, **terms)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class ProfileAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user
