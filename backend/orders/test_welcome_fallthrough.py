"""The welcome discount lands on every line the campaigns left with nothing —
except a line that paid for someone's free candle, whose reward is the free
candle. The free line then says which welcome offer it replaced.

Set up as production is: buy two 11.3 oz, the free one is an 8 oz. The 11.3
oz candles are the offer's campaign; the 8 oz are reward candles no campaign
claims. Shipping is mocked where build_order calls it, so nothing reaches
Shippo.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from candles.models import Candle, CandleVariant, Category, Offer
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
def returning(other_user):
    Order.objects.create(user=other_user, status=Order.Status.PAID)
    return other_user


@pytest.fixture
def shop(db):
    big_cat = Category.objects.create(name="Multiple-wick candles")
    small_cat = Category.objects.create(name="Single-wick candles")

    def make(cat, name, price, size):
        candle = Candle.objects.create(category=cat, name=name, size=size, stock_qty=1000)
        return CandleVariant.objects.create(
            candle=candle, size=size, price=price, stock_qty=1000, is_active=True
        )

    big = [make(big_cat, n, "21.99", "11.3 oz") for n in ("Mango Island", "Matcha Chill", "Tidal Bore")]
    small = [make(small_cat, n, "18.49", "8 oz") for n in ("Mango Island", "Matcha Chill")]

    offer = Offer.objects.create(title="Buy Two Get Three", kind=Offer.Kind.B1G2, priority=10)
    offer.candles.add(*[v.candle for v in big])
    offer.reward_candles.add(*[v.candle for v in small])

    Offer.objects.create(
        title="Welcome 10%",
        kind=Offer.Kind.NEW_SHOPPER,
        discount_percent=10,
        apply_globally=True,
        show_badge=False,
        priority=30,
    )

    return {"big": big, "small": small, "offer": offer}


def _lines(basket):
    return [
        {"variant_id": v.id, "candle": v.candle, "unit_price": v.price, "quantity": q}
        for v, q in basket
    ]


def _cart(user, basket):
    """What the cart shows: {variant_id: (pays, label, free, replaces)} and
    the total. Checked against the stored order and the preview endpoint,
    which must say the same."""
    priced = price_basket(user=user, lines=_lines(basket))
    lines = {
        line.variant_id: (
            line.line_total - line.discount_amount,
            line.discount_label,
            line.free_quantity,
            line.replaces_label,
        )
        for line in priced.lines
    }

    with patch(
        "orders.serializers.resolve_shipping_cost", return_value=(Decimal("8.40"), None)
    ):
        order = build_order(
            user=user,
            lines=[{"variant_id": v.id, "quantity": q} for v, q in basket],
            shipping=ADDRESS,
        )
    for item in order.items.all():
        pays, label, free, _ = lines[item.variant_id]
        assert (item.unit_price * item.quantity - item.discount_amount, item.discount_label, item.free_quantity) == (pays, label, free)
    order.delete()

    client = APIClient()
    client.force_authenticate(user=user)
    preview = client.post(
        "/api/orders/price-preview/",
        {"items": [{"variant_id": v.id, "quantity": q} for v, q in basket]},
        format="json",
    ).json()
    assert Decimal(preview["items_total"]) == priced.items_total
    assert {l["variant_id"]: l["replaces_label"] for l in preview["lines"]} == {
        vid: line[3] for vid, line in lines.items()
    }

    return lines, priced.items_total


@pytest.mark.django_db
class TestTheCartMockUps:
    """The five baskets shown before this was built."""

    def test_one_11_3_oz_gets_the_welcome_discount(self, shop, user):
        mango = shop["big"][0]

        lines, total = _cart(user, [(mango, 1)])

        assert lines[mango.id] == (Decimal("19.79"), "Welcome 10%", 0, "")
        assert total == Decimal("19.79")

    def test_two(self, shop, user):
        mango = shop["big"][0]

        lines, total = _cart(user, [(mango, 2)])

        assert lines[mango.id] == (Decimal("39.58"), "Welcome 10%", 0, "")
        assert total == Decimal("39.58")

    def test_three_with_no_8_oz_keep_it_all(self, shop, user):
        mango = shop["big"][0]

        lines, total = _cart(user, [(mango, 3)])

        assert lines[mango.id] == (Decimal("59.37"), "Welcome 10%", 0, "")
        assert total == Decimal("59.37")

    def test_two_and_a_free_8_oz_switches_to_the_free_candle(self, shop, user):
        mango, small = shop["big"][0], shop["small"][0]

        lines, total = _cart(user, [(mango, 2), (small, 1)])

        assert lines[mango.id] == (Decimal("43.98"), "", 0, "")
        assert lines[small.id] == (Decimal("0.00"), "Buy Two Get Three", 1, "Welcome 10%")
        assert total == Decimal("43.98")

    def test_three_on_one_line_all_lose_it(self, shop, user):
        """One promotion per line: the line paid, so the leftover unit on it
        pays full price too."""
        mango, small = shop["big"][0], shop["small"][0]

        lines, total = _cart(user, [(mango, 3), (small, 1)])

        assert lines[mango.id] == (Decimal("65.97"), "", 0, "")
        assert total == Decimal("65.97")


@pytest.mark.django_db
class TestWhoPays:
    def test_on_separate_lines_the_line_that_did_not_pay_keeps_it(self, shop, user):
        """Equal prices: the two highest variant ids pay, as the free unit is
        picked. The lowest keeps its 10%."""
        mango, matcha, tidal = shop["big"]
        small = shop["small"][0]

        lines, total = _cart(user, [(mango, 1), (matcha, 1), (tidal, 1), (small, 1)])

        assert lines[mango.id][:2] == (Decimal("19.79"), "Welcome 10%")
        assert lines[matcha.id][:2] == (Decimal("21.99"), "")
        assert lines[tidal.id][:2] == (Decimal("21.99"), "")
        assert total == Decimal("63.77")

    def test_dearer_units_pay_first(self, shop, user):
        """A 30.00 11.3 oz and two 21.99: the 30.00 and one 21.99 pay."""
        mango, matcha, _ = shop["big"]
        small = shop["small"][0]
        dear = CandleVariant.objects.create(
            candle=Candle.objects.create(category=mango.candle.category, name="Oud", stock_qty=9),
            size="11.3 oz", price="30.00", stock_qty=9, is_active=True,
        )
        shop["offer"].candles.add(dear.candle)

        lines, _ = _cart(user, [(dear, 1), (mango, 1), (matcha, 1), (small, 1)])

        assert lines[dear.id][1] == ""
        assert lines[matcha.id][1] == ""
        assert lines[mango.id][1] == "Welcome 10%"

    def test_a_returning_shopper_sees_no_replaced_note(self, shop, returning):
        mango, small = shop["big"][0], shop["small"][0]

        lines, total = _cart(returning, [(mango, 2), (small, 1)])

        assert lines[small.id] == (Decimal("0.00"), "Buy Two Get Three", 1, "")
        assert total == Decimal("43.98")


@pytest.mark.django_db
class TestOtherCampaigns:
    def test_a_percentage_campaign_still_never_stacks(self, shop, user):
        mango = shop["big"][0]
        spooky = Offer.objects.create(
            title="Spooky Season Offer", kind=Offer.Kind.HOLIDAY, discount_percent=10, priority=5
        )
        spooky.candles.add(mango.candle)

        lines, _ = _cart(user, [(mango, 1)])

        assert lines[mango.id][:2] == (Decimal("19.79"), "Spooky Season Offer")

    def test_an_offer_without_a_reward_group_follows_the_same_rule(self, shop, user, category):
        """Mango, Matcha, Tidal 8 oz in one offer, plus Lemon: Tidal is free,
        Mango and Matcha pay for it and Lemon — not needed — keeps 10%."""
        spring = Offer.objects.create(title="Spring", kind=Offer.Kind.B1G2, priority=1)
        variants = []
        for name in ("Mango", "Matcha", "Tidal", "Lemon"):
            candle = Candle.objects.create(category=category, name=name, stock_qty=9)
            spring.candles.add(candle)
            variants.append(CandleVariant.objects.create(
                candle=candle, size="8 oz", price="18.49", stock_qty=9, is_active=True
            ))
        # Lemon is cheapest so it's outside the trio.
        lemon = variants[3]
        lemon.price = "15.00"
        lemon.save()
        mango, matcha, tidal, _ = variants

        lines, total = _cart(user, [(v, 1) for v in variants])

        assert lines[tidal.id] == (Decimal("0.00"), "Spring", 1, "Welcome 10%")
        assert lines[mango.id][:2] == (Decimal("18.49"), "")
        assert lines[matcha.id][:2] == (Decimal("18.49"), "")
        assert lines[lemon.id][:2] == (Decimal("13.50"), "Welcome 10%")
        assert total == Decimal("50.48")


@pytest.mark.django_db
class TestTheModal:
    def _ask(self, user, *basket):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.post(
            "/api/orders/offer-progress/",
            {"items": [{"variant_id": v.id, "quantity": q} for v, q in basket]},
            format="json",
        ).json()["promotions"]

    def test_it_says_when_the_free_candle_replaces_the_welcome_discount(self, shop, user):
        [promotion] = self._ask(user, (shop["big"][0], 2))

        assert promotion["needed"] == 1
        assert promotion["replaces_label"] == "Welcome 10%"

    def test_not_for_a_shopper_without_one(self, shop, returning):
        [promotion] = self._ask(returning, (shop["big"][0], 2))

        assert promotion["replaces_label"] == ""

    def test_the_card_shows_full_price_for_the_11_3_oz(self, shop, user, api_client):
        api_client.force_authenticate(user=user)
        rows = {r["id"]: r for r in api_client.get("/api/candles/candles/").json()}
        mango = shop["big"][0]

        assert rows[mango.candle_id]["discount_price"] is None
        assert rows[mango.candle_id]["variants"][0]["display_price"] == "21.99"
