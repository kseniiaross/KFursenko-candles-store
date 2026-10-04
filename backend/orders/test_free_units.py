"""Buy-two-get-three marks whole units free, on the lines that hold them.

What the cart shows ("Tidal Bore — Free", "Mango Island ×3 · 1 free") is
what the order stores: each line's discount is exactly its free units at its
own price. When several units share the free price, the free one is on the
line with the highest variant id — never decided by basket order, so the
same basket marks the same candle free in the cart, at checkout and on the
stored order.

Shipping is mocked where build_order calls it, so nothing reaches Shippo.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from candles.models import Candle, CandleVariant, Offer
from orders.discounts import price_basket
from orders.models import Order
from orders.serializers import build_order

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


@pytest.fixture
def make(db, category):
    """make("18.49", "18.49") -> variants in creation order (ascending ids),
    each its own candle, all in one buy-two-get-three offer."""
    offer = Offer.objects.create(title="Buy Two Get Three", kind=Offer.Kind.B1G2)

    def _make(*prices):
        variants = []
        for price in prices:
            candle = Candle.objects.create(
                category=category, name=f"Candle {Candle.objects.count()}", stock_qty=1000
            )
            offer.candles.add(candle)
            variants.append(
                CandleVariant.objects.create(
                    candle=candle, size="8 oz", price=price, stock_qty=1000, is_active=True
                )
            )
        return variants

    return _make


def _lines(basket):
    return [
        {"variant_id": v.id, "candle": v.candle, "unit_price": v.price, "quantity": q}
        for v, q in basket
    ]


def _free(user, basket):
    """{variant_id: free_quantity} from the engine, checked against the
    stored order and the preview endpoint, which must all agree."""
    priced = price_basket(user=user, lines=_lines(basket))
    engine = {line.variant_id: line.free_quantity for line in priced.lines}

    for line in priced.lines:
        assert line.discount_amount == line.unit_price * line.free_quantity

    with patch(
        "orders.serializers.resolve_shipping_cost", return_value=(Decimal("8.40"), None)
    ):
        order = build_order(
            user=user,
            lines=[{"variant_id": v.id, "quantity": q} for v, q in basket],
            shipping=ADDRESS,
        )
    stored = {item.variant_id: item.free_quantity for item in order.items.all()}
    assert stored == engine

    client = APIClient()
    client.force_authenticate(user=user)
    preview = client.post(
        "/api/orders/price-preview/",
        {"items": [{"variant_id": v.id, "quantity": q} for v, q in basket]},
        format="json",
    ).json()
    assert {l["variant_id"]: l["free_quantity"] for l in preview["lines"]} == engine

    # The order API names items by candle; each candle here has one variant.
    detail = client.get(f"/api/orders/{order.pk}/").json()
    by_candle = {v.candle_id: engine[v.id] for v, _ in basket}
    assert {i["candle_id"]: i["free_quantity"] for i in detail["items"]} == by_candle

    return {vid: n for vid, n in engine.items() if n}


@pytest.mark.django_db
class TestWhichUnitIsFree:
    def test_three_equal_candles_the_highest_variant_id_is_free(self, make, user):
        a, b, c = make("18.49", "18.49", "18.49")

        assert _free(user, [(a, 1), (b, 1), (c, 1)]) == {c.id: 1}

    def test_basket_order_does_not_change_it(self, make, user):
        a, b, c = make("18.49", "18.49", "18.49")

        assert _free(user, [(c, 1), (a, 1), (b, 1)]) == {c.id: 1}
        assert _free(user, [(b, 1), (c, 1), (a, 1)]) == {c.id: 1}

    def test_three_of_one_candle_is_one_line_with_one_free(self, make, user):
        """Case 1: no separate row to show as free; the line carries it."""
        (a,) = make("18.49")

        assert _free(user, [(a, 3)]) == {a.id: 1}

        line = price_basket(user=user, lines=_lines([(a, 3)])).lines[0]
        assert line.line_total - line.discount_amount == Decimal("36.98")

    def test_six_equal_two_free_on_the_two_highest_ids(self, make, user):
        """Case 2, equal prices: Mango x2, Matcha x2, Lemon, Tidal."""
        mango, matcha, lemon, tidal = make("18.49", "18.49", "18.49", "18.49")

        assert _free(user, [(mango, 2), (matcha, 2), (lemon, 1), (tidal, 1)]) == {
            tidal.id: 1,
            lemon.id: 1,
        }

    def test_two_free_units_can_land_on_one_line(self, make, user):
        a, b = make("18.49", "18.49")

        # Six units, two free; the highest id holds four, so both free
        # units are on it.
        assert _free(user, [(a, 2), (b, 4)]) == {b.id: 2}

    def test_mixed_prices_the_cheapest_of_each_trio_whatever_the_ids(self, make, user):
        """Case 2, mixed prices: 60 50 40 | 30 20 10 -> 40 and 10 free.
        Created cheapest-first, so price — not id — must decide."""
        ten, twenty, thirty, forty, fifty, sixty = make(
            "10.00", "20.00", "30.00", "40.00", "50.00", "60.00"
        )

        free = _free(
            user,
            [(sixty, 1), (fifty, 1), (forty, 1), (thirty, 1), (twenty, 1), (ten, 1)],
        )

        assert free == {forty.id: 1, ten.id: 1}

    def test_free_unit_comes_from_the_line_at_the_free_price(self, make, user):
        """30, 30, 20 -> the 20 is free even though the 30s have the higher id."""
        b, a = make("20.00", "30.00")

        assert _free(user, [(a, 2), (b, 1)]) == {b.id: 1}

    def test_a_fourth_unit_outside_the_trio_pays(self, make, user):
        """40 30 20 | 10 -> the 20 is free, not the 10."""
        forty, thirty, twenty, ten = make("40.00", "30.00", "20.00", "10.00")

        assert _free(user, [(forty, 1), (thirty, 1), (twenty, 1), (ten, 1)]) == {
            twenty.id: 1
        }

    def test_two_units_earn_nothing(self, make, user):
        a, b = make("18.49", "18.49")

        assert _free(user, [(a, 1), (b, 1)]) == {}


@pytest.mark.django_db
def test_the_order_page_in_the_admin_shows_each_lines_discount(make, user, client):
    from accounts.models import User

    a, b, c = make("18.49", "18.49", "18.49")
    with patch(
        "orders.serializers.resolve_shipping_cost", return_value=(Decimal("8.40"), None)
    ):
        order = build_order(
            user=user,
            lines=[{"variant_id": v.id, "quantity": 1} for v in (a, b, c)],
            shipping=ADDRESS,
        )

    boss = User.objects.create_superuser(email="boss@example.com", password="pw-12345!")
    client.force_login(boss)
    page = client.get(f"/admin/orders/order/{order.pk}/change/").content.decode()

    assert "Free quantity" in page
    assert "Buy Two Get Three" in page
    assert Order.objects.get(pk=order.pk).items.get(variant=c).free_quantity == 1
