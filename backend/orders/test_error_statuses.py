"""Mistakes a shopper can make, and requests that aren't theirs to make,
answer 400 or 404 with a reason — never a 500, and never anything about
our code, database or keys.

Found by the monkey test: an address the shipping code can't read during
order creation, and order ids that aren't numbers. The rest came from
probing every endpoint the same way.
"""

import re
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from candles.models import Candle, CandleVariant
from cart.models import Cart, CartItem
from orders.models import Order
from shipping.client import ShippoError

ADDRESS = {
    "full_name": "Jane Doe", "line1": "1 Main St", "line2": "", "city": "Brooklyn",
    "state": "NY", "postal_code": "11201", "country": "US", "phone": "",
}

# What must never reach a shopper: code, file paths, queries, keys.
LEAK = re.compile(
    r"Traceback|\.py\b|/Users/|site-packages|normalize|COUNTRIES|SELECT |"
    r"sk_(test|live)|whsec_|SHIPPO|token",
    re.IGNORECASE,
)


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _assert_clean(response):
    assert not LEAK.search(response.content.decode()), response.content


@pytest.fixture
def variant(db, category):
    candle = Candle.objects.create(category=category, name="Mango Island", stock_qty=10)
    return CandleVariant.objects.create(
        candle=candle, size="11.3 oz", price="21.99", stock_qty=10, is_active=True,
    )


@pytest.fixture
def cart_with(user, variant):
    cart, _ = Cart.objects.get_or_create(user=user)
    return CartItem.objects.create(cart=cart, variant=variant, quantity=1)


class UndeliverableShippo:
    """Shippo saying the address exists on paper but can't be delivered to."""

    def __init__(self, *args, **kwargs):
        pass

    def create_shipment(self, payload):
        return {
            "object_id": "shp_1",
            "status": "SUCCESS",
            "address_to": {
                "validation_results": {
                    "is_valid": False,
                    "messages": [{"text": "Street number is missing"}],
                }
            },
            "rates": [],
        }


# ======================================================
# An address the shop can't ship to
# ======================================================
def _create(client, variant, shipping, *, from_cart=False):
    if from_cart:
        return client.post("/api/orders/from-cart/", {"shipping": shipping}, format="json")

    return client.post(
        "/api/orders/",
        {"items": [{"variant_id": variant.id, "quantity": 1}], "shipping": shipping},
        format="json",
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("cart_with")
class TestAddressDuringOrderCreation:
    @pytest.mark.parametrize("from_cart", [False, True], ids=["items", "cart"])
    @pytest.mark.parametrize(
        "field, value, says",
        [
            ("state", "Narnia", "isn't a US state"),
            ("country", "Atlantis", "can't ship to 'Atlantis'"),
        ],
    )
    def test_an_address_we_cant_read_is_a_400_that_says_what_to_fix(
        self, user, variant, from_cart, field, value, says
    ):
        response = _create(_client(user), variant, {**ADDRESS, field: value}, from_cart=from_cart)

        assert response.status_code == 400, response.content
        assert says in response.json()["shipping"]
        _assert_clean(response)

        # Nothing created or reserved, and the cart is still there to retry.
        assert Order.objects.count() == 0
        variant.refresh_from_db()
        assert variant.stock_qty == 10
        assert CartItem.objects.filter(cart__user=user).count() == 1

    @pytest.mark.parametrize("from_cart", [False, True], ids=["items", "cart"])
    def test_an_undeliverable_address_is_a_400_with_the_carriers_reason(
        self, user, variant, from_cart
    ):
        with patch("shipping.services.ShippoClient", UndeliverableShippo):
            response = _create(_client(user), variant, ADDRESS, from_cart=from_cart)

        assert response.status_code == 400, response.content
        assert response.json() == {"shipping": "Street number is missing"}
        assert Order.objects.count() == 0

    def test_a_candle_with_no_weight_still_sells_at_the_flat_rate(
        self, user, variant, settings, caplog
    ):
        # Our product data, not the shopper's address: never their error.
        variant.weight_oz = Decimal("0")
        variant.save(update_fields=["weight_oz"])

        with patch("shipping.services.ShippoClient", UndeliverableShippo), caplog.at_level(
            "ERROR"
        ):
            response = _create(_client(user), variant, ADDRESS)

        assert response.status_code == 201, response.content
        assert Decimal(response.json()["shipping_amount"]) == settings.SHIPPING_FALLBACK_RATE
        assert any("no shipping weight" in r.getMessage() for r in caplog.records)


@pytest.mark.django_db
class TestAddressWhenQuoting:
    def _rates(self, user, variant, shipping):
        return _client(user).post(
            "/api/shipping/rates/",
            {"items": [{"variant_id": variant.id, "quantity": 1}], "shipping": shipping},
            format="json",
        )

    def test_an_unknown_country_doesnt_name_our_code(self, user, variant):
        response = self._rates(user, variant, {**ADDRESS, "country": "Atlantis"})

        assert response.status_code == 400
        assert "can't ship to 'Atlantis'" in response.json()["shipping"]
        _assert_clean(response)

    def test_a_shippo_failure_keeps_its_reason_in_the_log(self, user, variant):
        class Down(UndeliverableShippo):
            def create_shipment(self, payload):
                raise ShippoError("Shippo returned 401", status_code=401, payload={"detail": "token"})

        with patch("shipping.services.ShippoClient", Down):
            response = self._rates(user, variant, ADDRESS)

        assert response.status_code == 502
        assert "reason" not in response.json()
        _assert_clean(response)

    def test_a_candle_with_no_weight_is_unavailable_not_the_shoppers_fault(
        self, user, variant
    ):
        variant.weight_oz = Decimal("0")
        variant.save(update_fields=["weight_oz"])

        with patch("shipping.services.ShippoClient", UndeliverableShippo):
            response = self._rates(user, variant, ADDRESS)

        assert response.status_code == 503
        assert "Variant" not in response.content.decode()


# ======================================================
# Someone else's order, and ids that aren't ids
# ======================================================
@pytest.mark.django_db
class TestSomeoneElsesOrder:
    @pytest.fixture
    def order(self, user):
        return Order.objects.create(
            user=user, status=Order.Status.PENDING, total_amount="42.50",
            stripe_payment_intent_id="pi_theirs",
        )

    def test_reading_or_cancelling_it_is_a_404(self, other_user, order):
        client = _client(other_user)

        assert client.get(f"/api/orders/{order.pk}/").status_code == 404
        assert client.post(f"/api/orders/{order.pk}/cancel/").status_code == 404

        order.refresh_from_db()
        assert order.status == Order.Status.PENDING

    def test_paying_for_it_is_a_404(self, other_user, order):
        response = _client(other_user).post(
            "/api/orders/create-intent/", {"order_id": order.pk}, format="json"
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "order_id",
        ["abc", "1; DROP TABLE orders_order", "1.5", 1.5, True, {"id": 1}, [1], "", None],
    )
    def test_an_order_id_that_isnt_a_number_is_a_400(self, other_user, order_id):
        response = _client(other_user).post(
            "/api/orders/create-intent/", {"order_id": order_id}, format="json"
        )

        assert response.status_code == 400, response.content
        assert response.json() == {"error": "Missing or invalid order_id"}


# ======================================================
# A body that isn't a JSON object
# ======================================================
@pytest.mark.django_db
@pytest.mark.parametrize("body", ["[1, 2]", '"text"', "7", "null"])
@pytest.mark.parametrize(
    "method, url",
    [
        ("post", "/api/orders/"),
        ("post", "/api/orders/create-intent/"),
        ("patch", "/api/cart/items/{item}/"),
    ],
)
def test_a_body_that_isnt_an_object_is_a_400(user, cart_with, method, url, body):
    response = getattr(_client(user), method)(
        url.format(item=cart_with.pk), data=body, content_type="application/json"
    )

    assert response.status_code == 400, response.content
    assert response.json() == {"detail": "Expected a JSON object."}
