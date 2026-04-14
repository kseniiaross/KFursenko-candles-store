from rest_framework import generics, permissions
from .models import NewsletterSubscriber
from .serializers import NewsletterSubscriberSerializer


class SubscribeAPIView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = NewsletterSubscriberSerializer
    queryset = NewsletterSubscriber.objects.all()