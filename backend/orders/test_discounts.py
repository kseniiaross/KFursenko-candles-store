"""Discounts as build_order applies them, end to end.

Shipping is mocked at the point build_order calls it, so nothing here talks
to Shippo, and build_order never calls Stripe. Expected amounts are worked
out by hand in the comments rather than recomputed with the code under test.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from candles.models import Candle, CandleVariant, Offer
from orders.models import Order
from orders.serializers import build_order

SHIPPING = Decimal("8.00")

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

# None of these divide evenly into the proportional split, so every
# multi-line case exercises the rounding.
PRICES = ["19.99", "24.49", "31.17", "12.33", "27.81", "16.05"]


def _variant(category, name, price):
    candle = Candle.objects.create(
        category=category, name=name, price=price, stock_qty=50
    )
    return CandleVariant.objects.create(
        candle=candle, size="8 oz", price=price, stock_qty=50, is_active=True
    )


def _build(user, lines):
    with patch(
        "orders.serializers.resolve_shipping_cost", return_value=(SHIPPING, None)
    ):
        return build_order(user=user, lines=lines, shipping=ADDRESS)


def _assert_lines_sum_to_order(order):
    items = list(order.items.all())
    line_sum = sum((item.discount_amount for item in items), Decimal("0.00"))

    assert line_sum == order.discount_amount
    assert order.total_amount == (
        order.subtotal_amount - order.discount_amount + SHIPPING
    )

    for item in items:
        assert Decimal("0.00") <= item.discount_amount <= item.line_total()
        assert item.discount_amount == item.discount_amount.quantize(Decimal("0.01"))


@pytest.fixture
def b2g3(db):
    return Offer.objects.create(
        title="Spring Buy 2 Get 3",
        kind=Offer.Kind.B1G2,
        apply_globally=True,
    )


@pytest.mark.django_db
class TestBuyTwoGetThree:
    @pytest.mark.parametrize(
        "prices, quantities, expected_free",
        [
            # Two candles earn nothing.
            (["19.99", "24.49"], [1, 1], "0.00"),
            # 31.17, 24.49, 19.99 -> the trio's cheapest, 19.99, is free.
            (["19.99", "24.49", "31.17"], [1, 1, 1], "19.99"),
            # 31.17, 24.49, 19.99 | 12.33 -> one full trio; the fourth candle
            # is not in one, so 19.99 (not 12.33) is free.
            (["19.99", "24.49", "31.17", "12.33"], [1, 1, 1, 1], "19.99"),
            # 31.17, 27.81, 24.49 | 19.99, 16.05, 12.33 -> 24.49 + 12.33.
            (PRICES, [1, 1, 1, 1, 1, 1], "36.82"),
            # Quantity on one line counts as separate candles:
            # 24.49, 19.99, 19.99 -> 19.99 free.
            (["19.99", "24.49"], [2, 1], "19.99"),
        ],
        ids=["two", "three", "four", "six", "three-via-quantity"],
    )
    def test_free_candles_and_per_line_split(
        self, user, category, b2g3, prices, quantities, expected_free
    ):
        variants = [
            _variant(category, f"Candle {i}", price) for i, price in enumerate(prices)
        ]

        order = _build(
            user,
            [
                {"variant_id": v.id, "quantity": qty}
                for v, qty in zip(variants, quantities)
            ],
        )

        assert order.discount_amount == Decimal(expected_free)
        _assert_lines_sum_to_order(order)

        if order.discount_amount > 0:
            assert order.discount_label == b2g3.title
            assert all(
                item.discount_label == b2g3.title for item in order.items.all()
            )
        else:
            assert order.discount_label == ""
            assert all(item.discount_label == "" for item in order.items.all())


@pytest.mark.django_db
def test_percentage_rounds_per_line_and_lines_still_sum(user, category):
    """10% of three 10.05 lines.

    Per line: 1.005 -> 1.01 each, 3.03 in all. Rounded once on the order it
    would be 3.015 -> 3.02. The per-line figure is what build_order now
    charges, and it is the one the stored lines add up to.
    """
    Offer.objects.create(
        title="Welcome 10%",
        kind=Offer.Kind.NEW_SHOPPER,
        discount_percent=10,
        apply_globally=True,
    )
    variants = [_variant(category, f"Plain {i}", "10.05") for i in range(3)]

    order = _build(user, [{"variant_id": v.id, "quantity": 1} for v in variants])

    assert order.discount_amount == Decimal("3.03")
    assert [item.discount_amount for item in order.items.all()] == [
        Decimal("1.01")
    ] * 3
    _assert_lines_sum_to_order(order)


@pytest.mark.django_db
def test_mixed_basket_label_is_truncated_to_the_column(user, category):
    """B2G3 on three candles, the welcome offer on a fourth, plain one.

    Both apply, so the summary label joins both titles — longer than the
    160-character column. It must be cut rather than fail the order.
    """
    long_title = "Spring " + "Bouquet " * 18  # 151 characters
    spring = Offer.objects.create(title=long_title[:160], kind=Offer.Kind.B1G2)
    Offer.objects.create(
        title="Welcome 10%",
        kind=Offer.Kind.NEW_SHOPPER,
        discount_percent=10,
        apply_globally=True,
    )

    promo = [_variant(category, f"Spring {i}", p) for i, p in enumerate(PRICES[:3])]
    for variant in promo:
        spring.candles.add(variant.candle)
    plain = _variant(category, "Plain", "10.05")

    order = _build(
        user, [{"variant_id": v.id, "quantity": 1} for v in [*promo, plain]]
    )

    # 19.99 free from the trio, plus 10% of 10.05 = 1.005 -> 1.01.
    assert order.discount_amount == Decimal("21.00")
    _assert_lines_sum_to_order(order)

    max_len = Order._meta.get_field("discount_label").max_length
    assert len(order.discount_label) == max_len
    assert order.discount_label.startswith("Spring Bouquet")

    plain_item = order.items.get(variant=plain)
    assert plain_item.discount_amount == Decimal("1.01")
    assert plain_item.discount_label == "Welcome 10%"
