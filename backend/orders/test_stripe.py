import hashlib
import hmac
import time

import pytest

# stripe_webhook() itself uses select_for_update() once past signature
# verification, which SQLite doesn't support (see cart/test_cart.py and
# orders/test_orders.py for the same limitation) - the two guard-clause
# tests below return before ever touching the database, so they run fine
# here; tests that need to reach the event-handling code are marked skip.
SELECT_FOR_UPDATE_SKIP_REASON = "requires PostgreSQL"

WEBHOOK_URL = "/api/orders/webhook/"
TEST_SECRET = "whsec_test_dummy"


def _sign(payload: str, secret: str = TEST_SECRET) -> str:
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload}"
    sig = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


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


@pytest.mark.skip(reason=SELECT_FOR_UPDATE_SKIP_REASON)
@pytest.mark.django_db
class TestStripeWebhookMetadataGuard:
    def test_event_with_no_metadata_key_is_ignored_not_500(self, api_client, settings):
        # Regression test: data["metadata"] used to be accessed with plain
        # bracket indexing, so an event with no "metadata" key at all (e.g.
        # a payment_intent type this app didn't create) raised an uncaught
        # KeyError -> 500 instead of being safely ignored.
        settings.STRIPE_WEBHOOK_SECRET = TEST_SECRET

        payload = (
            '{"id": "evt_1", "type": "payment_intent.succeeded", '
            '"data": {"object": {"id": "pi_no_metadata"}}}'
        )

        response = api_client.post(
            WEBHOOK_URL,
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=_sign(payload),
        )

        assert response.status_code == 200
