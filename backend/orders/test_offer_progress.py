"""The cart prompt: how close a basket is to a free candle, and what to add.

Suggestions list every eligible candle — the ones already in the basket
first, as the exact variant the basket holds, so picking one raises that
line's quantity instead of adding a second line in another size.
"""

import pytest

from candles.models import Candle, CandleVariant, Offer

URL = "/api/orders/offer-progress/"


def _candle(category, name, *sizes, stock=50, bestseller=False):
    """sizes: (size, price) pairs; returns (candle, [variants])."""
    candle = Candle.objects.create(
        category=category, name=name, stock_qty=stock, is_bestseller=bestseller
    )
    variants = [
        CandleVariant.objects.create(
            candle=candle, size=size, price=price, stock_qty=stock, is_active=True
        )
        for size, price in (sizes or [("8 oz", "18.49")])
    ]
    return candle, variants


@pytest.fixture
def spring(db, category):
    offer = Offer.objects.create(title="Buy Two Get Three", kind=Offer.Kind.B1G2)
    candles = {}
    for name in ("Mango Island", "Matcha Chill", "Sweet Lemon Dew", "Tidal Bore"):
        candle, variants = _candle(category, name)
        offer.candles.add(candle)
        candles[name] = variants[0]
    return offer, candles


def _ask(api_client, *lines):
    response = api_client.post(
        URL,
        {"items": [{"variant_id": v.id, "quantity": q} for v, q in lines]},
        format="json",
    )
    assert response.status_code == 200
    return response.json()["promotions"]


def _names(promotion):
    return [s["name"] for s in promotion["suggestions"]]


@pytest.mark.django_db
class TestSuggestions:
    def test_basket_candles_come_first_then_every_other_eligible_one(
        self, api_client, spring, category
    ):
        _, c = spring
        _candle(category, "Not In Any Offer")

        [promotion] = _ask(api_client, (c["Matcha Chill"], 1), (c["Mango Island"], 1))

        assert promotion["needed"] == 1
        assert _names(promotion) == [
            "Mango Island", "Matcha Chill",  # in the basket, tie -> by name
            "Sweet Lemon Dew", "Tidal Bore",  # the rest
        ]

    def test_most_held_comes_first(self, api_client, spring):
        _, c = spring

        # 1 + 4 = 5 qualifying: one free so far, one more for the next trio.
        [promotion] = _ask(api_client, (c["Mango Island"], 1), (c["Tidal Bore"], 4))

        assert promotion["needed"] == 1
        assert _names(promotion)[:2] == ["Tidal Bore", "Mango Island"]

    def test_basket_candle_is_suggested_as_the_size_in_the_basket(
        self, api_client, spring, category
    ):
        offer, c = spring
        candle, (small, large) = _candle(
            category, "Coconut", ("8 oz", "18.49"), ("11.3 oz", "21.99")
        )
        offer.candles.add(candle)

        [promotion] = _ask(api_client, (large, 1), (c["Mango Island"], 1))

        coconut = [s for s in promotion["suggestions"] if s["name"] == "Coconut"]
        assert [s["variant_id"] for s in coconut] == [large.id]

    def test_no_stock_for_one_more_leaves_it_out(self, api_client, spring, category):
        offer, _ = spring
        candle, (last_two,) = _candle(category, "Last Two", stock=2)
        offer.candles.add(candle)

        [promotion] = _ask(api_client, (last_two, 2))

        assert "Last Two" not in _names(promotion)

    def test_capped_at_six_with_the_basket_kept(self, api_client, spring, category):
        offer, c = spring
        for i in range(6):
            candle, _ = _candle(category, f"Extra {i}", bestseller=True)
            offer.candles.add(candle)

        [promotion] = _ask(api_client, (c["Tidal Bore"], 1), (c["Sweet Lemon Dew"], 1))

        names = _names(promotion)
        assert len(names) == 6
        assert names[:2] == ["Sweet Lemon Dew", "Tidal Bore"]

    def test_three_in_the_basket_is_a_complete_trio(self, api_client, spring):
        _, c = spring

        assert _ask(api_client, (c["Mango Island"], 3)) == []

    def test_candles_outside_the_offer_are_never_suggested(
        self, api_client, spring, category
    ):
        _, c = spring
        _, (outsider,) = _candle(category, "Not In Any Offer")

        [promotion] = _ask(api_client, (c["Mango Island"], 1), (outsider, 1))

        assert promotion["in_cart"] == 1
        assert "Not In Any Offer" not in _names(promotion)
