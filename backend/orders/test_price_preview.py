"""POST /api/orders/price-preview/ shows what checkout will charge.

Checked against build_order for every basket in the production-price
scenario (shared with test_pricing), as a guest, a first-time shopper and a
returning one. Shipping is mocked where build_order calls it.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from candles.models import Candle, CandleVariant
from orders.test_pricing import BASKETS, _charge, returning, shop  # noqa: F401 — shared fixtures

URL = "/api/orders/price-preview/"


def _client(user=None):
    client = APIClient()
    if user:
        client.force_authenticate(user=user)
    return client


def _preview(client, *lines):
    response = client.post(
        URL,
        {"items": [{"variant_id": v.id if hasattr(v, "id") else v, "quantity": q} for v, q in lines]},
        format="json",
    )
    assert response.status_code == 200, response.content
    return response.json()


@pytest.mark.django_db
class TestPreviewIsWhatCheckoutCharges:
    @pytest.mark.parametrize("basket_name", BASKETS)
    @pytest.mark.parametrize("shopper", ["guest", "first-time", "returning"])
    def test_line_by_line(self, shop, user, returning, basket_name, shopper):
        viewer = {"guest": None, "first-time": user, "returning": returning}[shopper]
        # Checkout needs an account, and a guest gets no welcome offer — the
        # same prices a returning shopper is charged.
        charged_as = returning if shopper == "guest" else viewer
        basket = BASKETS[basket_name](shop)

        preview = _preview(_client(viewer), *basket)
        order = _charge(charged_as, basket)

        items = {item.variant_id: item for item in order.items.all()}
        assert {line["variant_id"] for line in preview["lines"]} == set(items)

        for line in preview["lines"]:
            item = items[line["variant_id"]]
            assert Decimal(line["unit_price"]) == item.unit_price
            assert line["quantity"] == item.quantity
            assert Decimal(line["line_total"]) == item.line_total()
            assert Decimal(line["discount_amount"]) == item.discount_amount
            assert line["discount_label"] == item.discount_label
            assert Decimal(line["line_total_after_discount"]) == (
                item.line_total() - item.discount_amount
            )

        assert Decimal(preview["subtotal"]) == order.subtotal_amount
        assert Decimal(preview["discount"]) == order.discount_amount
        assert Decimal(preview["items_total"]) == (
            order.total_amount - order.shipping_amount - order.tax_amount
        )
        assert preview["label"] == order.discount_label
        assert preview["unavailable"] == []

    def test_the_mixed_basket_on_production_prices(self, shop, user, returning):
        mixed = BASKETS["mixed"](shop)

        assert _preview(_client(user), *mixed)["discount"] == "21.64"
        assert _preview(_client(returning), *mixed)["discount"] == "20.34"
        # A guest is priced like a returning shopper: no welcome offer.
        assert _preview(_client(), *mixed)["discount"] == "20.34"


@pytest.mark.django_db
class TestInput:
    def test_repeated_variants_are_merged_like_build_order(self, shop, returning):
        mango = shop["spring"][0]

        preview = _preview(_client(returning), (mango, 1), (mango, 2))
        order = _charge(returning, [(mango, 3)])

        [line] = preview["lines"]
        assert line["quantity"] == 3
        assert Decimal(preview["items_total"]) == order.total_amount - order.shipping_amount

    def test_gone_and_switched_off_variants_are_listed_not_priced(
        self, shop, returning, category
    ):
        candle = Candle.objects.create(category=category, name="Retired", stock_qty=5)
        off = CandleVariant.objects.create(
            candle=candle, size="8 oz", price="30.00", stock_qty=5, is_active=False
        )
        plain = shop["plain"]

        preview = _preview(_client(returning), (plain, 1), (off, 1), (999999, 1))

        assert preview["unavailable"] == sorted([off.id, 999999])
        assert [line["variant_id"] for line in preview["lines"]] == [plain.id]
        assert preview["subtotal"] == "12.99"

    def test_an_empty_basket_is_all_zeros(self, db):
        preview = _preview(_client())

        assert preview["lines"] == []
        assert preview["subtotal"] == preview["discount"] == preview["items_total"] == "0.00"
        assert preview["label"] == ""

    def test_a_zero_quantity_is_refused(self, shop):
        response = _client().post(
            URL, {"items": [{"variant_id": shop["plain"].id, "quantity": 0}]}, format="json"
        )

        assert response.status_code == 400


@pytest.mark.django_db
def test_offer_prompt_suggestions_carry_the_checkout_price(shop, user):
    """Every suggestion's display_price is what one costs at checkout."""
    a, b = shop["spring"][:2]

    response = _client(user).post(
        "/api/orders/offer-progress/",
        {"items": [{"variant_id": a.id, "quantity": 1}, {"variant_id": b.id, "quantity": 1}]},
        format="json",
    )
    [promotion] = response.json()["promotions"]

    assert promotion["suggestions"]
    for suggestion in promotion["suggestions"]:
        variant = CandleVariant.objects.get(pk=suggestion["variant_id"])
        order = _charge(user, [(variant, 1)])
        item = order.items.get()
        assert Decimal(suggestion["display_price"]) == item.unit_price - item.discount_amount
