import pytest

# stripe_webhook() itself uses select_for_update() once past signature
# verification, which SQLite doesn't support (see cart/test_cart.py and
# orders/test_orders.py for the same limitation) - but the two checks below
# both return before ever touching the database, so they run fine here.

WEBHOOK_URL = "/api/orders/webhook/"


@pytest.mark.django_db
class TestStripeWebhookSecretGuard:
    def test_returns_500_when_secret_not_configured(self, api_client, settings):
        settings.STRIPE_WEBHOOK_SECRET = ""

        response = api_client.post(
            WEBHOOK_URL,
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=whatever",
        )

        assert response.status_code == 500

    def test_rejects_bad_signature_when_secret_is_configured(self, api_client, settings):
        settings.STRIPE_WEBHOOK_SECRET = "whsec_test_dummy"

        response = api_client.post(
            WEBHOOK_URL,
            data=b'{"type": "payment_intent.succeeded"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=not-a-real-signature",
        )

        assert response.status_code == 400
