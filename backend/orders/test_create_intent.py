"""Payment set-up must work on the database production runs on.

create-intent locks the order while reading its shipment, which may not
exist (no label until after payment; none at all on the flat-rate
fallback). Postgres refuses FOR UPDATE on the nullable side of an outer
join, so every checkout failed in production while SQLite, which ignores
row locks, passed every test. Run this on Postgres — the suite's default.

Stripe and Shippo are mocked; nothing leaves the machine.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from candles.models import Candle, CandleVariant
from orders.serializers import build_order

URL = "/api/orders/create-intent/"

ADDRESS = {
    "full_name": "Jane Doe",
    "line1": "1 Main St",
    "line2": "",
    "city": "Brooklyn",
    "state": "NY",
    "postal_code": "11201",
    "country": "US",
    "phone": "",
}

USPS = {
    "rate_id": "rate_usps_ground",
    "carrier": "USPS",
    "service_level": "Ground Advantage",
    "amount": Decimal("7.85"),
    "currency": "USD",
}


@pytest.fixture
def variant(db, category):
    candle = Candle.objects.create(category=category, name="Mango Island", stock_qty=10)
    return CandleVariant.objects.create(
        candle=candle, size="11.3 oz", price="21.99", stock_qty=10, is_active=True
    )


def _order(user, variant, rate):
    with patch(
        "orders.serializers.resolve_shipping_cost",
        return_value=(rate["amount"] if rate else Decimal("15.00"), rate),
    ):
        return build_order(
            user=user,
            lines=[{"variant_id": variant.id, "quantity": 1}],
            shipping=ADDRESS,
        )


def _intent(**kwargs):
    return SimpleNamespace(
        id="pi_test",
        client_secret="pi_test_secret_abc",
        status="requires_payment_method",
        amount=kwargs.get("amount"),
        currency=kwargs.get("currency"),
    )


@pytest.mark.django_db(transaction=True)
class TestCreateIntent:
    """transaction=True: the view's atomic block and its lock run for real,
    not inside the test's wrapping transaction."""

    @pytest.mark.parametrize("rate", [USPS, None], ids=["usps-rate", "flat-rate-no-shipment"])
    def test_a_pending_order_gets_its_payment_form(self, auth_client, user, variant, rate):
        order = _order(user, variant, rate)

        with patch("orders.views_stripe.stripe.PaymentIntent.create", side_effect=_intent) as create:
            response = auth_client.post(URL, {"order_id": order.id}, format="json")

        assert response.status_code == 200, response.content
        assert response.json()["client_secret"] == "pi_test_secret_abc"

        order.refresh_from_db()
        assert order.stripe_payment_intent_id == "pi_test"

        sent = create.call_args.kwargs
        assert sent["amount"] == int(order.total_amount * 100)

        # The shipment is still read for the Stripe dashboard breakdown.
        if rate:
            assert sent["metadata"]["shipping_carrier"] == "USPS"
        else:
            assert "shipping_carrier" not in sent["metadata"]
