"""The single source for prices: what is shown is what is charged.

price_basket is the function build_order now charges with, and the one the
cart preview and the catalogue will show. These tests pin that the numbers
agree line by line, on the offer set and prices found in the production
catalogue (2026-10-04): buy-two-get-three on four 18.49 candles, a 10%
seasonal offer on another 18.49 candle, a 12.99 candle with no campaign, and
a 10% welcome offer.

Shipping is mocked where build_order calls it, so nothing reaches Shippo.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from candles.models import Candle, CandleVariant, Offer
from orders import discounts
from orders.discounts import compute_line_discounts, price_basket, unit_display_prices
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


def _variant(category, name, price):
    candle = Candle.objects.create(category=category, name=name, price=price, stock_qty=1000)
    return CandleVariant.objects.create(
        candle=candle, size="8 oz", price=price, stock_qty=1000, is_active=True
    )


@pytest.fixture
def shop(db, category):
    spring = [
        _variant(category, name, "18.49")
        for name in ("Mango Island", "Matcha Chill", "Sweet Lemon Dew", "Tidal Bore")
    ]
    mulled = _variant(category, "Mulled Wine", "18.49")
    plain = _variant(category, "Woman Body", "12.99")

    b2g3 = Offer.objects.create(title="Buy Two Get Three", kind=Offer.Kind.B1G2, priority=10)
    for variant in spring:
        b2g3.candles.add(variant.candle)

    spooky = Offer.objects.create(
        title="Spooky Season Offer", kind=Offer.Kind.HOLIDAY, discount_percent=10, priority=20
    )
    spooky.candles.add(mulled.candle)

    Offer.objects.create(
        title="Welcome 10%",
        kind=Offer.Kind.NEW_SHOPPER,
        discount_percent=10,
        apply_globally=True,
        show_badge=False,
        priority=30,
    )

    return {"spring": spring, "mulled": mulled, "plain": plain}


@pytest.fixture
def returning(other_user):
    Order.objects.create(user=other_user, status=Order.Status.PAID)
    return other_user


def _lines(basket):
    return [
        {"variant_id": v.id, "candle": v.candle, "unit_price": v.price, "quantity": q}
        for v, q in basket
    ]


def _charge(user, basket):
    with patch(
        "orders.serializers.resolve_shipping_cost", return_value=(Decimal("8.40"), None)
    ):
        return build_order(
            user=user,
            lines=[{"variant_id": v.id, "quantity": q} for v, q in basket],
            shipping=ADDRESS,
        )


BASKETS = {
    "one qualifying": lambda s: [(s["spring"][0], 1)],
    "two qualifying": lambda s: [(s["spring"][0], 1), (s["spring"][1], 1)],
    "three qualifying": lambda s: [(v, 1) for v in s["spring"][:3]],
    "six qualifying": lambda s: [
        (s["spring"][0], 2), (s["spring"][1], 2), (s["spring"][2], 1), (s["spring"][3], 1)
    ],
    "mixed": lambda s: [(v, 1) for v in s["spring"][:3]] + [(s["mulled"], 1), (s["plain"], 1)],
    "plain only": lambda s: [(s["plain"], 3)],
}


@pytest.mark.django_db
class TestPriceBasketIsWhatBuildOrderCharges:
    @pytest.mark.parametrize("basket_name", BASKETS)
    @pytest.mark.parametrize("shopper", ["first-time", "returning"])
    def test_line_by_line(self, shop, user, returning, basket_name, shopper):
        who = user if shopper == "first-time" else returning
        basket = BASKETS[basket_name](shop)

        preview = price_basket(user=who, lines=_lines(basket))
        order = _charge(who, basket)

        charged = {item.variant_id: item for item in order.items.all()}
        assert len(preview.lines) == len(charged)

        for line in preview.lines:
            item = charged[line.variant_id]
            assert line.unit_price == item.unit_price
            assert line.quantity == item.quantity
            assert line.discount_amount == item.discount_amount
            assert line.discount_label == item.discount_label

        assert preview.subtotal == order.subtotal_amount
        assert preview.discount == order.discount_amount
        assert preview.items_total == order.total_amount - order.shipping_amount - order.tax_amount
        assert preview.label == order.discount_label

    def test_known_totals_on_production_prices(self, shop, user, returning):
        mixed = _lines(BASKETS["mixed"](shop))

        # 18.49 free + 10% of 18.49 (1.85) + welcome 10% of 12.99 (1.30)
        assert price_basket(user=user, lines=mixed).discount == Decimal("21.64")
        # A returning shopper has no welcome offer.
        assert price_basket(user=returning, lines=mixed).discount == Decimal("20.34")
        # Two of the four 18.49 candles free.
        six = price_basket(user=returning, lines=_lines(BASKETS["six qualifying"](shop)))
        assert six.discount == Decimal("36.98")


@pytest.mark.django_db
class TestUnitDisplayPrices:
    def _all(self, shop):
        return [*shop["spring"], shop["mulled"], shop["plain"]]

    @pytest.mark.parametrize("shopper", ["first-time", "returning"])
    def test_each_variant_shows_what_one_of_it_costs_at_checkout(
        self, shop, user, returning, shopper
    ):
        who = user if shopper == "first-time" else returning
        variants = self._all(shop)

        shown = unit_display_prices(user=who, variants=variants)

        for variant in variants:
            order = _charge(who, [(variant, 1)])
            item = order.items.get()
            charged = item.unit_price - item.discount_amount

            if variant in shop["spring"]:
                # The one exception: a buy-two-get-three candle shows full
                # price. Alone it gets the welcome offer; paying for a free
                # candle it wouldn't, so the card doesn't promise it.
                assert shown[variant.id].display_price == Decimal(variant.price)
                assert charged <= Decimal(variant.price)
            else:
                assert shown[variant.id].display_price == charged

    def test_the_prices_the_audit_found_wrong(self, shop, user, returning):
        b2g3_candle, mulled, plain = shop["spring"][0], shop["mulled"], shop["plain"]

        first = unit_display_prices(user=user, variants=[b2g3_candle, mulled, plain])
        # One buy-two-get-three candle earns nothing on its own. Checkout
        # gives a first-time shopper 16.64 for it, but the card shows full
        # price: the welcome offer goes once it pays for a free candle.
        assert first[b2g3_candle.id].display_price == Decimal("18.49")
        assert first[mulled.id].display_price == Decimal("16.64")
        assert first[plain.id].display_price == Decimal("11.69")

        back = unit_display_prices(user=returning, variants=[b2g3_candle, mulled, plain])
        assert back[b2g3_candle.id].display_price == Decimal("18.49")
        assert back[mulled.id].display_price == Decimal("16.64")
        assert back[plain.id].display_price == Decimal("12.99")

    def test_labels_name_the_offer_that_applies(self, shop, user):
        shown = unit_display_prices(user=user, variants=[shop["mulled"], shop["plain"], shop["spring"][0]])

        assert shown[shop["mulled"].id].discount_label == "Spooky Season Offer"
        assert shown[shop["plain"].id].discount_label == "Welcome 10%"
        assert shown[shop["spring"][0].id].discount_label == ""

    def test_offers_are_looked_up_once_for_the_whole_batch(self, shop, user):
        with patch.object(
            discounts, "get_active_offers", wraps=discounts.get_active_offers
        ) as offers, patch.object(
            discounts, "get_welcome_offer", wraps=discounts.get_welcome_offer
        ) as welcome:
            unit_display_prices(user=user, variants=self._all(shop))

        assert offers.call_count == 1
        assert welcome.call_count == 1


@pytest.mark.django_db
def test_passing_no_welcome_offer_means_none(shop, user):
    """None is an answer ("this shopper gets none"), not "look it up"."""
    plain = shop["plain"]
    lines = _lines([(plain, 1)])

    looked_up, _ = compute_line_discounts(user=user, lines=lines)
    told_none, _ = compute_line_discounts(user=user, lines=lines, welcome_offer=None)

    assert looked_up[plain.id].amount == Decimal("1.30")
    assert plain.id not in told_none
