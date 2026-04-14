from django.urls import path
from .views import LumiereReplyView

urlpatterns = [
    path("reply/", LumiereReplyView.as_view(), name="lumiere-reply"),
]