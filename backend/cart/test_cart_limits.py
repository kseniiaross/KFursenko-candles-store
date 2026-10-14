"""Limits the cart shares with checkout, and what happens when it's used
fast or the stock moves underneath it.

A cart line holds at most MAX_LINE_QUANTITY (999), the most an order line
or the price preview accepts — a cart that held more would fail at
checkout with nothing on the cart page to say why.
"""

import threading

import pytest
from django.db import connection
from rest_framework.test import APIClient

from candles.models import Candle, CandleVariant
from cart.models import MAX_LINE_QUANTITY, Cart, CartItem
from orders.models import Order

ADDRESS = {
    "full_name": "Jane Doe", "line1": "1 Main St", "line2": "", "city": "Brooklyn",
    "state": "NY", "postal_code": "11201", "country": "US", "phone": "",
}


@pytest.fixture
def plenty(db, category):
    """More in stock than one line may hold, so only the cap can refuse."""
    candle = Candle.objects.create(category=category, name="Tidal Bore", stock_qty=5000)
    return CandleVariant.objects.create(
        candle=candle, size="8 oz", price="18.49", stock_qty=5000, is_active=True
    )


def _item(user, variant, quantity):
    cart, _ = Cart.objects.get_or_create(user=user)
    return CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)


@pytest.mark.django_db
class TestLineCap:
    def test_adding_past_the_cap_is_refused_and_says_so(self, auth_client, user, plenty):
        _item(user, plenty, MAX_LINE_QUANTITY)

        response = auth_client.post(
            "/api/cart/items/add/", {"variant_id": plenty.id, "quantity": 1}, format="json"
        )

        assert response.status_code == 400
        assert "up to 999" in response.json()["quantity"]
        assert CartItem.objects.get().quantity == MAX_LINE_QUANTITY

    def test_a_single_add_over_the_cap_is_refused(self, auth_client, plenty):
        response = auth_client.post(
            "/api/cart/items/add/", {"variant_id": plenty.id, "quantity": 1000}, format="json"
        )

        assert response.status_code == 400
        assert CartItem.objects.count() == 0

    def test_setting_a_quantity_over_the_cap_is_refused(self, auth_client, user, plenty):
        item = _item(user, plenty, 5)

        response = auth_client.patch(
            f"/api/cart/items/{item.pk}/", {"quantity": 1000}, format="json"
        )

        assert response.status_code == 400
        assert "up to 999" in response.json()["quantity"]
        item.refresh_from_db()
        assert item.quantity == 5

    def test_exactly_the_cap_is_fine(self, auth_client, user, plenty):
        item = _item(user, plenty, 5)

        response = auth_client.patch(
            f"/api/cart/items/{item.pk}/", {"quantity": MAX_LINE_QUANTITY}, format="json"
        )

        assert response.status_code == 200

    def test_merging_past_the_cap_stops_at_the_cap(self, auth_client, user, plenty):
        _item(user, plenty, 900)

        response = auth_client.post(
            "/api/cart/merge/",
            {"items": [{"variant_id": plenty.id, "quantity": 500}]},
            format="json",
        )

        assert response.status_code == 200
        assert CartItem.objects.get().quantity == MAX_LINE_QUANTITY

    def test_a_line_switched_off_since_it_went_in_cant_be_changed(
        self, auth_client, user, plenty
    ):
        item = _item(user, plenty, 1)
        plenty.is_active = False
        plenty.save(update_fields=["is_active"])

        response = auth_client.patch(f"/api/cart/items/{item.pk}/", {"quantity": 2}, format="json")

        assert response.status_code == 400
        assert "not available" in response.json()["variant_id"]


@pytest.mark.django_db
class TestSoldBetweenCartAndCheckout:
    """The candle sold while it sat in the cart. Checkout names it and says
    what to do; nothing is created or reserved."""

    def _checkout(self, user, variant, quantity):
        client = APIClient()
        client.force_authenticate(user)
        # Stock is checked before shipping is quoted, so no Shippo here.
        return client.post(
            "/api/orders/",
            {"items": [{"variant_id": variant.id, "quantity": quantity}], "shipping": ADDRESS},
            format="json",
        )

    def test_sold_out(self, user, plenty):
        plenty.stock_qty = 0
        plenty.save(update_fields=["stock_qty"])

        response = self._checkout(user, plenty, 1)

        assert response.status_code == 400
        assert response.json()["items"] == (
            "Tidal Bore / 8 oz has sold out. Please remove it from your cart."
        )
        assert Order.objects.count() == 0

    def test_fewer_left_than_in_the_cart(self, user, plenty):
        plenty.stock_qty = 2
        plenty.save(update_fields=["stock_qty"])

        response = self._checkout(user, plenty, 3)

        assert response.status_code == 400
        assert response.json()["items"] == (
            "Only 2 left of Tidal Bore / 8 oz. Please lower the quantity in your cart."
        )

    def test_switched_off(self, user, plenty):
        plenty.is_active = False
        plenty.save(update_fields=["is_active"])

        response = self._checkout(user, plenty, 1)

        assert response.status_code == 400
        assert "no longer available" in response.json()["items"]


@pytest.mark.django_db(transaction=True)
class TestAddingFast:
    """Two adds of the same candle at once, on separate connections, the
    way two quick clicks reach the server. Neither is lost or doubled, and
    neither fails — including the very first add, which also creates the
    cart."""

    def _race(self, user, variant, n=2):
        barrier = threading.Barrier(n)
        statuses = []

        def add():
            client = APIClient()
            client.force_authenticate(user)
            barrier.wait()
            try:
                response = client.post(
                    "/api/cart/items/add/",
                    {"variant_id": variant.id, "quantity": 1},
                    format="json",
                )
                statuses.append(response.status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=add) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return statuses

    def test_two_adds_at_once_make_two(self, user, plenty):
        statuses = self._race(user, plenty, n=4)

        assert statuses == [201] * 4
        assert Cart.objects.filter(user=user).count() == 1
        assert CartItem.objects.get().quantity == 4

    def test_adds_at_once_never_pass_the_stock(self, user, plenty):
        plenty.stock_qty = 2
        plenty.save(update_fields=["stock_qty"])

        statuses = self._race(user, plenty, n=4)

        assert sorted(statuses) == [201, 201, 400, 400]
        assert CartItem.objects.get().quantity == 2
