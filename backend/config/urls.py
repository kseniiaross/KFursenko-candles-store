from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)


def home(request):
    return HttpResponse("Welcome to the Candles Backend API!")


urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),

    path("api/accounts/", include("accounts.urls")),
    path("api/candles/", include("candles.urls")),
    path("api/cart/", include("cart.urls")),
    path("api/orders/", include("orders.urls")),
    path("api/shipping/", include("shipping.urls")),
    path("api/newsletter/", include("newsletter.urls")),
    path("api/lumiere/", include("lumiere.urls")),

    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
