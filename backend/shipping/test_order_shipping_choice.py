"""What an order charges for shipping, given the rate the shopper picked.

The token only says which service the shopper chose. The order is quoted
afresh for its own candles and address, and that quote's price and rate
are what it charges and stores — so a token quoted for one candle can't
pay the shipping on fifty, and the label is bought for the address the
order ships to.

- Picked service in the fresh quote, same price or cheaper: charged that.
- Dearer now: 400, so the shopper sees the new price before paying.
- Service gone, or a token Shippo doesn't know: 400, choose again.
- Shippo unreachable: the flat rate, so an outage doesn't stop a sale.

A fake Shippo client prices each quote from the parcels it is given and
remembers what every rate token was quoted for. Nothing leaves the machine.
"""

import itertools
from decimal import Decimal
from unittest.mock import patch

import pytest

from candles.models import Candle, CandleVariant
from orders.models import Order
from shipping.client import ShippoError, ShippoNotConfigured
from shipping.models import Shipment

BROOKLYN = {
    "full_name": "Jane Doe", "line1": "1 Main St", "line2": "", "city": "Brooklyn",
    "state": "NY", "postal_code": "11201", "country": "US", "phone": "",
}
MANHATTAN = {**BROOKLYN, "line1": "350 5th Ave", "city": "New York", "postal_code": "10118"}

FLAT = Decimal("15.00")


class FakeShippo:
    """Stands in for ShippoClient. Ground costs 6.00 plus 10c an ounce;
    Priority four dollars more, unless `services` says otherwise."""

    ids = itertools.count(1)
    rates: dict = {}
    quoted_for: dict = {}
    services = ("Ground Advantage", "Priority Mail")
    get_rate_error = None
    create_error = None

    def __init__(self, *args, **kwargs):
        pass

    def create_shipment(self, payload):
        if FakeShippo.create_error:
            raise FakeShippo.create_error

        weight = sum(Decimal(p["weight"]) for p in payload["parcels"])
        ground = (Decimal("6.00") + weight / 10).quantize(Decimal("0.01"))
        prices = {"Ground Advantage": ground, "Priority Mail": ground + 4}
        rates = []

        for service in FakeShippo.services:
            rate_id = f"rate_{next(FakeShippo.ids)}"
            rate = {
                "object_id": rate_id, "provider": "USPS",
                "servicelevel": {"name": service}, "amount": str(prices[service]),
                "currency": "USD",
            }
            FakeShippo.rates[rate_id] = rate
            FakeShippo.quoted_for[rate_id] = {
                "zip": payload["address_to"]["zip"], "parcels": len(payload["parcels"]),
                "weight": weight,
            }
            rates.append(rate)

        return {
            "object_id": f"shp_{next(FakeShippo.ids)}", "status": "SUCCESS",
            "address_to": {"validation_results": {"is_valid": True}}, "rates": rates,
        }

    def get_rate(self, rate_id):
        if FakeShippo.get_rate_error:
            raise FakeShippo.get_rate_error

        if rate_id not in FakeShippo.rates:
            raise ShippoError("Shippo returned 404", status_code=404, payload={"detail": "Not found"})

        return FakeShippo.rates[rate_id]


@pytest.fixture(autouse=True)
def shippo():
    FakeShippo.rates, FakeShippo.quoted_for = {}, {}
    FakeShippo.services = ("Ground Advantage", "Priority Mail")
    FakeShippo.get_rate_error = FakeShippo.create_error = None

    with patch("shipping.services.ShippoClient", FakeShippo):
        yield FakeShippo


@pytest.fixture
def variant(db, category):
    candle = Candle.objects.create(category=category, name="Mango Island", stock_qty=100)
    return CandleVariant.objects.create(
        candle=candle, size="11.3 oz", price="21.99", stock_qty=100, is_active=True,
        weight_oz="18.00", length_in="3.00", width_in="3.00", height_in="4.00",
    )


def _quote(client, variant, quantity, address=BROOKLYN, service="Ground Advantage"):
    """The rate checkout would offer the shopper: (token, amount)."""
    response = client.post(
        "/api/shipping/rates/",
        {"shipping": address, "items": [{"variant_id": variant.id, "quantity": quantity}]},
        format="json",
    )
    assert response.status_code == 200, response.content
    rate = next(r for r in response.json() if r["service_level"] == service)
    return rate["rate_id"], Decimal(rate["amount"])


def _order(client, variant, quantity, token, address=BROOKLYN):
    return client.post(
        "/api/orders/",
        {
            "items": [{"variant_id": variant.id, "quantity": quantity}],
            "shipping": address,
            "shipping_rate_id": token,
        },
        format="json",
    )


def _refused(response, variant, stock=100):
    """A 400 the shopper can act on, and nothing created or reserved."""
    assert response.status_code == 400, response.content
    assert "shipping_rate_id" in response.json(), response.json()
    assert Order.objects.count() == 0
    variant.refresh_from_db()
    assert variant.stock_qty == stock


@pytest.mark.django_db
class TestTheTokenOnlyPicksTheService:
    def test_a_token_quoted_for_one_candle_does_not_pay_for_fifty(self, auth_client, variant):
        token, one_candle = _quote(auth_client, variant, 1)

        response = _order(auth_client, variant, 50, token)

        # Fifty candles cost more to ship: the shopper is told the new price
        # instead of being charged the one-candle rate.
        _refused(response, variant)
        assert "$" in response.json()["shipping_rate_id"][0]

        # Choosing again from a quote for fifty goes through at that price.
        token, fifty_candles = _quote(auth_client, variant, 50)
        assert fifty_candles > one_candle

        response = _order(auth_client, variant, 50, token)

        assert response.status_code == 201, response.content
        order = Order.objects.get()
        assert order.shipping_amount == fifty_candles

        stored = FakeShippo.quoted_for[order.shipment.rate_id]
        assert stored["parcels"] > 1 and stored["weight"] >= 50 * 18

    def test_the_label_rate_is_for_the_address_the_order_ships_to(self, auth_client, variant):
        """A Brooklyn quote used for a Manhattan order: same price here, so
        the order goes through — with a rate quoted for Manhattan."""
        token, amount = _quote(auth_client, variant, 1, BROOKLYN)

        response = _order(auth_client, variant, 1, token, MANHATTAN)

        assert response.status_code == 201, response.content
        shipment = Order.objects.get().shipment
        assert shipment.rate_id != token
        assert FakeShippo.quoted_for[shipment.rate_id]["zip"] == "10118"
        assert shipment.amount == amount

    def test_cheaper_now_is_charged_the_lower_price(self, auth_client, variant):
        token, five_candles = _quote(auth_client, variant, 5)

        response = _order(auth_client, variant, 1, token)

        assert response.status_code == 201, response.content
        assert Order.objects.get().shipping_amount < five_candles

    def test_the_service_picked_is_the_service_charged(self, auth_client, variant):
        token, priority = _quote(auth_client, variant, 1, service="Priority Mail")

        response = _order(auth_client, variant, 1, token)

        assert response.status_code == 201, response.content
        assert Order.objects.get().shipment.service_level == "Priority Mail"
        assert Order.objects.get().shipping_amount == priority


@pytest.mark.django_db
class TestChooseAgain:
    def test_a_token_shippo_does_not_know_is_a_400_not_the_flat_rate(self, auth_client, variant):
        _refused(_order(auth_client, variant, 1, "rate_made_up"), variant)

    @pytest.mark.parametrize("status", [400, 404])
    def test_shippo_rejecting_the_token_is_a_400(self, auth_client, variant, status):
        FakeShippo.get_rate_error = ShippoError(f"Shippo returned {status}", status_code=status)

        _refused(_order(auth_client, variant, 1, "rate_x"), variant)

    def test_a_service_no_longer_offered_is_a_400(self, auth_client, variant):
        token, _ = _quote(auth_client, variant, 1, service="Priority Mail")
        FakeShippo.services = ("Ground Advantage",)

        _refused(_order(auth_client, variant, 1, token), variant)


@pytest.mark.django_db
class TestShippoUnreachable:
    """Only Shippo being down falls back to the flat rate."""

    @pytest.mark.parametrize(
        "error",
        [
            ShippoError("Shippo request failed: ConnectionError"),
            ShippoError("Shippo returned 503", status_code=503),
            ShippoError("Shippo returned 429", status_code=429),
            ShippoError("Shippo returned 401", status_code=401),
            ShippoNotConfigured("no token"),
        ],
        ids=["no-connection", "503", "429", "401-our-token", "not-configured"],
    )
    def test_checking_the_token_fails_flat_rate(self, auth_client, variant, error):
        token, _ = _quote(auth_client, variant, 1)
        FakeShippo.get_rate_error = error

        response = _order(auth_client, variant, 1, token)

        assert response.status_code == 201, response.content
        assert Order.objects.get().shipping_amount == FLAT
        assert not Shipment.objects.exists()

    def test_requoting_fails_flat_rate(self, auth_client, variant):
        token, _ = _quote(auth_client, variant, 1)
        FakeShippo.create_error = ShippoError("Shippo returned 502", status_code=502)

        response = _order(auth_client, variant, 1, token)

        assert response.status_code == 201, response.content
        assert Order.objects.get().shipping_amount == FLAT


@pytest.mark.django_db
def test_no_token_is_charged_the_cheapest_rate_for_the_order(auth_client, variant):
    response = _order(auth_client, variant, 1, "")

    assert response.status_code == 201, response.content
    order = Order.objects.get()
    assert order.shipment.service_level == "Ground Advantage"
    assert FakeShippo.quoted_for[order.shipment.rate_id]["zip"] == "11201"
