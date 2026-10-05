"""Buy-two-get-three with a reward group: "buy two 11.3 oz, the free one is
an 8 oz".

The rule is the one the offer always had — a free unit is paid for by two
units costing at least as much — with one more condition: the free unit
comes from the reward group and the two payers from the qualifying group.
An offer with no reward group must price every basket exactly as before.

Shipping is mocked where build_order calls it, so nothing reaches Shippo.
"""

import itertools
import random
import time
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from candles.models import Candle, CandleVariant, Category, Offer
from orders.discounts import EITHER, FREE_ONLY, PAYS, _free_units, price_basket
from orders.serializers import build_order

BIG, SMALL = "21.99", "18.49"

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


def _old_free_prices(prices):
    """The rule before reward groups: dearest first, every third free."""
    ordered = sorted(prices, reverse=True)
    return [price for index, price in enumerate(ordered) if index % 3 == 2]


def _runs(units):
    """(price, role) units -> runs as the engine sorts them."""
    counts = {}
    for price, role in units:
        counts[(price, role)] = counts.get((price, role), 0) + 1
    keys = sorted(counts, key=lambda key: (-key[0], key[1]))
    return [(price, role, counts[(price, role)]) for price, role in keys]


def _best_possible(runs):
    """Brute force: the largest saving any pairing allows."""
    best = Decimal("0")
    for frees in itertools.product(*[range(q + 1) if r != PAYS else [0] for _, r, q in runs]):
        free = sorted(
            (p for (p, _, _), x in zip(runs, frees) for _ in range(x)), reverse=True
        )
        payers = [
            p for (p, r, q), x in zip(runs, frees) if r != FREE_ONLY for _ in range(q - x)
        ]
        if all(sum(pp >= f for pp in payers) >= 2 * (i + 1) for i, f in enumerate(free)):
            best = max(best, sum(free, Decimal("0")))
    return best


def _plain_walk(runs):
    """Reference for _free_units: try every free count in every run."""
    after_free = [sum(q for _, r, q in runs[i:] if r != PAYS) for i in range(len(runs) + 1)]
    best = {0: (0, ())}
    for index, (price, role, quantity) in enumerate(runs):
        cents, cap, step = int(price * 100), 2 * after_free[index + 1], {}
        for payers, (saving, counts) in best.items():
            for free in range((0 if role == PAYS else quantity) + 1):
                after = {PAYS: payers + quantity, FREE_ONLY: payers - 2 * free}.get(
                    role, payers + quantity - 3 * free
                )
                if after < 0:
                    break
                after = min(after, cap)
                candidate = (saving + cents * free, counts + (free,))
                if after not in step or candidate > step[after]:
                    step[after] = candidate
        best = step
    return list(max(best.values())[1])


class TestTheRule:
    def test_without_a_reward_group_it_is_exactly_the_old_rule(self):
        rng = random.Random(1)
        prices = [Decimal(p) for p in ("10.00", "12.99", "18.49", "21.99", "30.00")]

        for _ in range(3000):
            units = [rng.choice(prices) for _ in range(rng.randint(0, 12))]
            runs = _runs([(p, EITHER) for p in units])

            free = sorted(
                (p for (p, _, _), x in zip(runs, _free_units(runs)) for _ in range(x)),
                reverse=True,
            )

            assert free == _old_free_prices(units), units

    def test_it_finds_the_best_pairing(self):
        rng = random.Random(2)
        prices = [Decimal(p) for p in ("10.00", "18.49", "21.99")]

        for _ in range(1500):
            units = [
                (rng.choice(prices), rng.choice((PAYS, EITHER, FREE_ONLY)))
                for _ in range(rng.randint(0, 7))
            ]
            runs = _runs(units)
            saving = sum(
                (p * x for (p, _, _), x in zip(runs, _free_units(runs))), Decimal("0")
            )

            assert saving == _best_possible(runs), units

    def test_it_agrees_with_the_plain_walk_on_quantities(self):
        """_free_units uses a sliding window; this is the same walk done
        unit-count by unit-count, which is easy to read and slow."""
        rng = random.Random(3)
        prices = [Decimal(p) for p in ("10.00", "18.49", "21.99", "30.00")]

        for _ in range(800):
            units = [
                (rng.choice(prices), rng.choice((PAYS, EITHER, FREE_ONLY)))
                for _ in range(rng.randint(0, 6))
            ]
            runs = [(p, r, rng.randint(1, 9)) for p, r, _ in _runs(units)]

            assert _free_units(runs) == _plain_walk(runs), runs

    def test_a_huge_basket_prices_quickly(self):
        runs = _runs(
            [(Decimal(p), r) for p in ("30.00", "21.99", "18.49", "12.99", "10.00")
             for r in (PAYS, EITHER, FREE_ONLY)]
        )
        runs = [(p, r, 999) for p, r, _ in runs]

        started = time.perf_counter()
        _free_units(runs)

        assert time.perf_counter() - started < 2


@pytest.fixture
def groups(db):
    """Qualifying: the 11.3 oz category. Reward: the 8 oz category."""
    big_cat = Category.objects.create(name="Multiple-wick candles")
    small_cat = Category.objects.create(name="Single-wick candles")

    offer = Offer.objects.create(
        title="Buy Two Get Three", kind=Offer.Kind.B1G2, priority=10, badge_text="B2G3"
    )
    offer.categories.add(big_cat)
    offer.reward_categories.add(small_cat)

    def make(cat, name, price, size):
        candle = Candle.objects.create(category=cat, name=name, stock_qty=1000)
        return CandleVariant.objects.create(
            candle=candle, size=size, price=price, stock_qty=1000, is_active=True
        )

    big = [make(big_cat, f"Big {i}", BIG, "11.3 oz") for i in range(6)]
    small = [make(small_cat, f"Small {i}", SMALL, "8 oz") for i in range(6)]

    return offer, big, small, make, small_cat


def _price(user, basket):
    """Price through the engine, the stored order and the preview, which
    must agree. Returns (items_total, {variant_id: free_quantity})."""
    lines = [
        {"variant_id": v.id, "candle": v.candle, "unit_price": v.price, "quantity": q}
        for v, q in basket
    ]
    priced = price_basket(user=user, lines=lines)
    free = {line.variant_id: line.free_quantity for line in priced.lines if line.free_quantity}

    with patch(
        "orders.serializers.resolve_shipping_cost", return_value=(Decimal("8.40"), None)
    ):
        order = build_order(
            user=user,
            lines=[{"variant_id": v.id, "quantity": q} for v, q in basket],
            shipping=ADDRESS,
        )
    assert {i.variant_id: i.free_quantity for i in order.items.all() if i.free_quantity} == free

    client = APIClient()
    client.force_authenticate(user=user)
    preview = client.post(
        "/api/orders/price-preview/",
        {"items": [{"variant_id": v.id, "quantity": q} for v, q in basket]},
        format="json",
    ).json()
    assert Decimal(preview["items_total"]) == priced.items_total

    return priced.items_total, free


@pytest.mark.django_db
class TestABasketOfSix:
    @pytest.mark.parametrize(
        "bigs, smalls, free_smalls, pays",
        [
            (6, 0, 0, "131.94"),
            (5, 1, 1, "109.95"),
            (4, 2, 2, "87.96"),
            (3, 3, 1, "102.95"),
            (2, 4, 1, "99.45"),
            (1, 5, 0, "114.44"),
            (0, 6, 0, "110.94"),
        ],
    )
    def test_the_free_candle_comes_from_the_reward_group(
        self, groups, user, bigs, smalls, free_smalls, pays
    ):
        _, big, small, _, _ = groups
        basket = [(v, 1) for v in big[:bigs]] + [(v, 1) for v in small[:smalls]]

        total, free = _price(user, basket)

        assert total == Decimal(pays)
        assert sum(free.values()) == free_smalls
        assert set(free) <= {v.id for v in small}

    def test_the_free_one_is_the_highest_variant_id_among_equals(self, groups, user):
        _, big, small, _, _ = groups

        _, free = _price(user, [(big[0], 2), (small[0], 1), (small[1], 1)])

        assert free == {small[1].id: 1}

    def test_a_reward_dearer_than_its_payers_is_never_free(self, groups, user):
        """Decision 1: "buy two 8 oz, get an 11.3 oz free" gives nothing."""
        offer, big, small, _, small_cat = groups
        offer.categories.set([small_cat])
        offer.reward_categories.set([big[0].candle.category])

        _, free = _price(user, [(small[0], 1), (small[1], 1), (big[0], 1)])

        assert free == {}


@pytest.mark.django_db
class TestRewardCandlesAndOtherPromotions:
    def test_a_reward_candle_another_campaign_claims_keeps_that_campaign(
        self, groups, user
    ):
        """Decision 2."""
        _, big, small, _, _ = groups
        spooky = Offer.objects.create(
            title="Spooky Season Offer", kind=Offer.Kind.HOLIDAY,
            discount_percent=10, priority=20,
        )
        spooky.candles.add(small[0].candle)

        lines = [
            {"variant_id": v.id, "candle": v.candle, "unit_price": v.price, "quantity": 1}
            for v in (big[0], big[1], small[0])
        ]
        line = price_basket(user=user, lines=lines).lines[2]

        assert line.free_quantity == 0
        assert line.discount_label == "Spooky Season Offer"
        assert line.discount_amount == Decimal("1.85")

    def test_a_reward_candle_keeps_the_welcome_discount_until_one_is_free(
        self, groups, user
    ):
        """Decision 3."""
        _, big, small, _, _ = groups
        Offer.objects.create(
            title="Welcome 10%", kind=Offer.Kind.NEW_SHOPPER,
            discount_percent=10, apply_globally=True,
        )

        def small_line(bigs):
            lines = [
                {"variant_id": v.id, "candle": v.candle, "unit_price": v.price, "quantity": q}
                for v, q in ((big[0], bigs), (small[0], 2))
            ]
            return price_basket(user=user, lines=lines).lines[1]

        # One big candle: nothing free, the 8 oz line takes the welcome 10%.
        alone = small_line(1)
        assert (alone.free_quantity, alone.discount_label) == (0, "Welcome 10%")
        assert alone.discount_amount == Decimal("3.70")

        # Two big: one 8 oz free; the line is the offer's, the other unit
        # pays full price.
        paired = small_line(2)
        assert (paired.free_quantity, paired.discount_label) == (1, "Buy Two Get Three")
        assert paired.discount_amount == Decimal(SMALL)


@pytest.mark.django_db
class TestStorefront:
    def test_badges_go_on_qualifying_candles_only(self, groups, api_client):
        _, big, small, _, _ = groups

        rows = {
            row["id"]: [b["slug"] for b in row["badges"]]
            for row in api_client.get("/api/candles/candles/").json()
        }

        assert rows[big[0].candle_id] == ["buy-two-get-three"]
        assert rows[small[0].candle_id] == []

    def _ask(self, api_client, *basket):
        response = api_client.post(
            "/api/orders/offer-progress/",
            {"items": [{"variant_id": v.id, "quantity": q} for v, q in basket]},
            format="json",
        )
        assert response.status_code == 200
        return response.json()["promotions"]

    def test_the_modal_suggests_reward_candles(self, groups, api_client):
        """Decision 4: two 11.3 oz in the basket, one 8 oz earns it."""
        _, big, small, _, _ = groups

        [promotion] = self._ask(api_client, (big[0], 2))

        assert promotion["reward_group"] is True
        assert promotion["needed"] == 1
        assert promotion["free_so_far"] == 0
        assert {s["variant_id"] for s in promotion["suggestions"]} <= {v.id for v in small}
        assert len(promotion["suggestions"]) == 6

    def test_a_reward_candle_that_would_be_charged_is_not_suggested(
        self, groups, api_client
    ):
        _, big, small, make, small_cat = groups
        make(small_cat, "Dear 8 oz", "25.00", "8 oz")

        [promotion] = self._ask(api_client, (big[0], 2))

        assert "Dear 8 oz" not in [s["name"] for s in promotion["suggestions"]]

    def test_the_basket_s_own_reward_candle_comes_first(self, groups, api_client):
        _, big, small, _, _ = groups

        [promotion] = self._ask(api_client, (big[0], 4), (small[3], 1))

        assert promotion["needed"] == 1
        assert promotion["suggestions"][0]["variant_id"] == small[3].id

    def test_one_qualifying_candle_needs_a_payer_and_a_reward(self, groups, api_client):
        _, big, _, _, _ = groups

        [promotion] = self._ask(api_client, (big[0], 1))

        assert promotion["needed"] == 2

    def test_a_complete_set_is_not_nudged(self, groups, api_client):
        _, big, small, _, _ = groups

        assert self._ask(api_client, (big[0], 2), (small[0], 1)) == []

    def test_reward_candles_alone_are_nudged_towards_payers(self, groups, api_client):
        _, _, small, _, _ = groups

        [promotion] = self._ask(api_client, (small[0], 1))

        assert promotion["needed"] == 2
        assert promotion["free_so_far"] == 0


@pytest.mark.django_db
def test_the_admin_offer_page_has_the_reward_group(groups, client):
    from accounts.models import User

    offer, *_ = groups
    boss = User.objects.create_superuser(email="boss@example.com", password="pw-12345!")
    client.force_login(boss)

    page = client.get(f"/admin/candles/offer/{offer.pk}/change/").content.decode()

    assert "Free candle (buy two, get three)" in page
    assert 'name="reward_categories"' in page
    assert 'name="reward_collections"' in page
    assert 'name="reward_candles"' in page
