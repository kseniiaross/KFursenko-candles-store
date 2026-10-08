"""POST /api/shipping/rates/ validates its input like an order does.

Quantity was uncapped: build_parcels builds one parcel per box, so 10**9
units meant ~140 million dicts and an out-of-memory kill. Variant ids and
quantities went through int() unvalidated, and address fields through
.strip(), so a wrong type was a 500. Every bad request must now be a 400
that never reaches the box-packer or Shippo.

quote_rates is mocked: nothing here calls Shippo, and on code without the
cap the oversized request reaches the mock instead of building parcels.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from candles.models import Candle, CandleVariant

URL = "/api/shipping/rates/"

ADDRESS = {
    "full_name": "Jane Doe",
    "line1": "1 Main St",
    "line2": "",
    "city": "Brooklyn",
    "state": "NY",
    "postal_code": "11201",
    "country": "US",
}

RATE = {
    "rate_id": "rate_1",
    "carrier": "USPS",
    "service_level": "Ground Advantage",
    "amount": Decimal("7.85"),
    "currency": "USD",
    "estimated_days": 4,
    "duration_terms": "",
}


@pytest.fixture
def variant(db, category):
    candle = Candle.objects.create(category=category, name="Mango Island", stock_qty=10)
    return CandleVariant.objects.create(
        candle=candle, size="11.3 oz", price="21.99", stock_qty=10, is_active=True,
        weight_oz="18.00", length_in="3.00", width_in="3.00", height_in="4.00",
    )


@pytest.fixture
def quote():
    with patch("shipping.views.quote_rates", return_value=[RATE]) as mocked:
        yield mocked


def _post(client, items, shipping=ADDRESS):
    return client.post(URL, {"shipping": shipping, "items": items}, format="json")


@pytest.mark.django_db
class TestQuantityCap:
    @pytest.mark.parametrize("quantity", [1000, 10**9, 10**20])
    def test_more_than_an_order_allows_is_refused_before_quoting(
        self, auth_client, variant, quote, quantity
    ):
        response = _post(auth_client, [{"variant_id": variant.id, "quantity": quantity}])

        assert response.status_code == 400, response.content
        quote.assert_not_called()

    def test_split_across_lines_is_still_capped(self, auth_client, variant, quote):
        """Two lines of 600 for the same candle are 1,200 of it."""
        response = _post(
            auth_client,
            [
                {"variant_id": variant.id, "quantity": 600},
                {"variant_id": variant.id, "quantity": 600},
            ],
        )

        assert response.status_code == 400, response.content
        quote.assert_not_called()

    def test_the_cap_itself_is_quoted(self, auth_client, variant, quote):
        response = _post(auth_client, [{"variant_id": variant.id, "quantity": 999}])

        assert response.status_code == 200, response.content
        [(_, kwargs)] = [(c.args, c.kwargs) for c in quote.call_args_list]
        assert [(v.id, q) for v, q in kwargs["lines"]] == [(variant.id, 999)]


@pytest.mark.django_db
class TestTypes:
    @pytest.mark.parametrize(
        "item",
        [
            {"variant_id": "", "quantity": 1},
            {"variant_id": "abc", "quantity": 1},
            {"variant_id": None, "quantity": 1},
            {"variant_id": [1], "quantity": 1},
            {"variant_id": {"a": 1}, "quantity": 1},
            {"variant_id": -1, "quantity": 1},
            {"quantity": 1},
            {"variant_id": "VARIANT", "quantity": "abc"},
            {"variant_id": "VARIANT", "quantity": None},
            {"variant_id": "VARIANT", "quantity": 0},
            {"variant_id": "VARIANT", "quantity": -1},
            {"variant_id": "VARIANT", "quantity": 1.5},
            {"variant_id": "VARIANT", "quantity": [1]},
            {"variant_id": "VARIANT"},
        ],
        ids=lambda item: ",".join(f"{k}={v!r}" for k, v in item.items()) or "empty",
    )
    def test_a_malformed_line_is_a_400(self, auth_client, variant, quote, item):
        item = {k: (variant.id if v == "VARIANT" else v) for k, v in item.items()}

        response = _post(auth_client, [item])

        assert response.status_code == 400, response.content
        quote.assert_not_called()

    @pytest.mark.parametrize("items", ["x", 5, {"variant_id": 1}, [5], ["x"]])
    def test_items_that_are_not_a_list_of_lines_are_a_400(self, auth_client, quote, items):
        response = _post(auth_client, items)

        assert response.status_code == 400, response.content
        quote.assert_not_called()

    @pytest.mark.parametrize(
        "field, value", [("postal_code", True), ("state", [1]), ("city", {"a": 1}), ("line1", None)]
    )
    def test_a_wrong_type_in_the_address_is_a_400(self, auth_client, variant, quote, field, value):
        response = _post(
            auth_client,
            [{"variant_id": variant.id, "quantity": 1}],
            shipping={**ADDRESS, field: value},
        )

        assert response.status_code == 400, response.content
        quote.assert_not_called()

    @pytest.mark.parametrize("shipping", ["x", 5, [ADDRESS], None])
    def test_an_address_that_is_not_an_object_is_a_400(self, auth_client, variant, quote, shipping):
        response = _post(auth_client, [{"variant_id": variant.id, "quantity": 1}], shipping=shipping)

        assert response.status_code == 400, response.content
        quote.assert_not_called()


@pytest.mark.django_db
class TestStillWorks:
    def test_a_numeric_zip_is_read_as_text(self, auth_client, variant, quote):
        response = _post(
            auth_client,
            [{"variant_id": variant.id, "quantity": 1}],
            shipping={**ADDRESS, "postal_code": 11201},
        )

        assert response.status_code == 200, response.content
        assert quote.call_args.kwargs["address_to"]["zip"] == "11201"

    def test_no_name_yet_still_quotes(self, auth_client, variant, quote):
        """Checkout asks for rates before the shopper has typed a name."""
        response = _post(
            auth_client,
            [{"variant_id": variant.id, "quantity": 1}],
            shipping={k: v for k, v in ADDRESS.items() if k != "full_name"},
        )

        assert response.status_code == 200, response.content

    def test_without_items_the_server_cart_is_quoted(self, auth_client, user, variant, quote):
        from cart.models import Cart, CartItem

        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, variant=variant, quantity=2)

        response = auth_client.post(URL, {"shipping": ADDRESS}, format="json")

        assert response.status_code == 200, response.content
        assert [(v.id, q) for v, q in quote.call_args.kwargs["lines"]] == [(variant.id, 2)]
