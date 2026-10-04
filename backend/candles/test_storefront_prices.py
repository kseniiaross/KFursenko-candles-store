"""The catalogue shows what checkout charges.

Every price the catalogue API returns — the card's sale price and each
variant's display_price — must equal what build_order charges for one of that
candle, for the shopper asking. Checked through the real API as a guest, a
first-time shopper and a returning one.

Shipping is mocked where build_order calls it, so nothing reaches Shippo.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from candles import serializers as candle_serializers
from candles.models import Candle, CandleVariant, Offer
from orders.models import Order
from orders.serializers import build_order

LIST_URL = "/api/candles/candles/"

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


def _candle(category, name, *prices, inactive=()):
    candle = Candle.objects.create(category=category, name=name, stock_qty=1000)
    for i, price in enumerate(prices):
        CandleVariant.objects.create(
            candle=candle,
            size=f"size {i}",
            price=price,
            stock_qty=1000,
            is_active=price not in inactive,
        )
    return candle


@pytest.fixture
def shop(db, category):
    """The production offer set: buy-two-get-three on spring candles, a 10%
    seasonal offer, a welcome 10% — plus a fixed-price offer, which checkout
    has never applied."""
    mango = _candle(category, "Mango Island", "18.49")
    matcha = _candle(category, "Matcha Chill", "18.49")
    mulled = _candle(category, "Mulled Wine", "18.49")
    plain = _candle(category, "Woman Body", "12.99")
    fixed = _candle(category, "Berry Grove", "18.49")
    two_sizes = _candle(category, "Tidal Bore", "18.49", "9.99", inactive=("9.99",))

    b2g3 = Offer.objects.create(title="Buy Two Get Three", kind=Offer.Kind.B1G2, priority=10)
    b2g3.candles.add(mango, matcha)

    spooky = Offer.objects.create(
        title="Spooky Season Offer", kind=Offer.Kind.HOLIDAY, discount_percent=10, priority=20
    )
    # Mango is in both campaigns: priority must pick buy-two-get-three, and
    # only that one may show.
    spooky.candles.add(mulled, mango, two_sizes)

    fixed_price = Offer.objects.create(
        title="Berry Fixed", kind=Offer.Kind.DISCOUNT, discounted_price="12.00", priority=25
    )
    fixed_price.candles.add(fixed)

    Offer.objects.create(
        title="Welcome 10%",
        kind=Offer.Kind.NEW_SHOPPER,
        discount_percent=10,
        apply_globally=True,
        show_badge=True,
        priority=30,
    )

    return {
        "mango": mango,
        "matcha": matcha,
        "mulled": mulled,
        "plain": plain,
        "fixed": fixed,
        "two_sizes": two_sizes,
    }


@pytest.fixture
def returning(other_user):
    Order.objects.create(user=other_user, status=Order.Status.PAID)
    return other_user


def _catalogue(api_client, user=None):
    if user:
        api_client.force_authenticate(user=user)
    response = api_client.get(LIST_URL)
    assert response.status_code == 200
    data = response.json()
    rows = data["results"] if isinstance(data, dict) else data
    return {row["slug"]: row for row in rows}


def _charge_one(user, variant):
    with patch(
        "orders.serializers.resolve_shipping_cost", return_value=(Decimal("8.40"), None)
    ):
        order = build_order(
            user=user,
            lines=[{"variant_id": variant.id, "quantity": 1}],
            shipping=ADDRESS,
        )
    item = order.items.get()
    return item.unit_price - item.discount_amount


@pytest.mark.django_db
class TestShownIsCharged:
    @pytest.mark.parametrize("shopper", ["guest", "first-time", "returning"])
    def test_every_variant_and_every_card(self, api_client, shop, user, returning, shopper):
        viewer = {"guest": None, "first-time": user, "returning": returning}[shopper]
        # A guest can't place an order; checkout treats them like a returning
        # shopper — no welcome offer — so that's whose charge they must match.
        charged_as = returning if shopper == "guest" else viewer

        catalogue = _catalogue(api_client, viewer)

        for candle in shop.values():
            row = catalogue[candle.slug]
            shown = {v["id"]: Decimal(v["display_price"]) for v in row["variants"]}

            active = [v for v in candle.variants.all() if v.is_active]
            for variant in active:
                assert shown[variant.id] == _charge_one(charged_as, variant), (
                    shopper, candle.name, variant.size
                )

            cheapest = min(active, key=lambda v: v.price)
            card = row["discount_price"]
            expected = _charge_one(charged_as, cheapest)
            if expected < cheapest.price:
                assert Decimal(str(card)) == expected, (shopper, candle.name)
            else:
                assert card is None, (shopper, candle.name)

    def test_the_prices_the_audit_found_wrong(self, api_client, shop, user):
        first = _catalogue(api_client, user)

        # Buy-two-get-three earns nothing on one candle, and keeps the
        # welcome offer off it: full price, no sale price.
        assert first["mango-island"]["discount_price"] is None
        assert first["mango-island"]["variants"][0]["display_price"] == "18.49"
        assert Decimal(str(first["mulled-wine"]["discount_price"])) == Decimal("16.64")
        assert Decimal(str(first["woman-body"]["discount_price"])) == Decimal("11.69")

    def test_a_fixed_price_is_never_shown(self, api_client, shop, user):
        row = _catalogue(api_client, user)["berry-grove"]

        assert row["discount_price"] is None
        assert row["variants"][0]["display_price"] == "18.49"

    def test_an_inactive_cheaper_size_does_not_set_the_card_price(self, api_client, shop):
        row = _catalogue(api_client)["tidal-bore"]
        by_price = {v["price"]: v for v in row["variants"]}

        # 10% of the active 18.49, not of the inactive 9.99 (which would be 8.99).
        assert Decimal(str(row["discount_price"])) == Decimal("16.64")
        assert by_price["9.99"]["is_active"] is False


@pytest.mark.django_db
class TestBadgesFollowCheckout:
    def _badges(self, row):
        return [b["slug"] for b in row["badges"]]

    def test_campaign_wins_and_only_it_shows(self, api_client, shop, user):
        catalogue = _catalogue(api_client, user)

        # Mango matches buy-two-get-three and Spooky; priority picks b2g3.
        assert self._badges(catalogue["mango-island"]) == ["buy-two-get-three"]
        assert self._badges(catalogue["mulled-wine"]) == ["spooky-season-offer"]

    def test_welcome_badge_only_where_checkout_gives_it(self, api_client, shop, user, returning):
        first = _catalogue(api_client, user)
        assert self._badges(first["woman-body"]) == ["welcome-10"]
        # A campaign candle never carries the welcome badge.
        assert "welcome-10" not in self._badges(first["matcha-chill"])

        api_client.force_authenticate(user=None)
        back = _catalogue(api_client, returning)
        assert self._badges(back["woman-body"]) == []


@pytest.mark.django_db
def test_offers_are_looked_up_once_per_catalogue_page(api_client, shop, user):
    api_client.force_authenticate(user=user)

    with patch.object(
        candle_serializers, "get_active_offers", wraps=candle_serializers.get_active_offers
    ) as offers, patch.object(
        candle_serializers, "get_welcome_offer", wraps=candle_serializers.get_welcome_offer
    ) as welcome:
        response = api_client.get(LIST_URL)

    assert response.status_code == 200
    assert offers.call_count == 1
    assert welcome.call_count == 1
