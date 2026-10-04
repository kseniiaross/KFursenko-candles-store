"""What happens to an order between checkout and payment.

Covers the welcome offer surviving an unpaid attempt, and stock going back on
the shelf when an order is cancelled — by the shopper, by staff, or by the
expiry job — or refunded before it ships.

No test here reaches Stripe or Shippo: shipping is mocked where build_order
calls it, and every Stripe call fails the test unless a test mocks it on
purpose.
"""

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe
from django.core.management import CommandError, call_command
from django.utils import timezone

from candles.models import Candle, CandleVariant, Offer
from orders.discounts import get_welcome_offer
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


@pytest.fixture(autouse=True)
def no_stripe():
    """Any Stripe call a test did not ask for is a failure, not a request."""
    unexpected = MagicMock(side_effect=AssertionError("unexpected Stripe call"))

    with patch.object(stripe.PaymentIntent, "cancel", unexpected), patch.object(
        stripe.PaymentIntent, "retrieve", unexpected
    ):
        yield


def stripe_cancels():
    """Stripe accepts the cancellation."""
    return patch.object(stripe.PaymentIntent, "cancel", MagicMock(return_value=None))


def stripe_refuses(intent_status):
    """Stripe won't cancel; a re-read shows why."""
    refuse = MagicMock(
        side_effect=stripe.InvalidRequestError("unexpected state", param=None)
    )
    reread = MagicMock(return_value=SimpleNamespace(status=intent_status))

    return (
        patch.object(stripe.PaymentIntent, "cancel", refuse),
        patch.object(stripe.PaymentIntent, "retrieve", reread),
    )


def stripe_has_no_such_intent():
    """Stripe answers 404 resource_missing — what an intent created under the
    test key looks like once the live key is in use."""
    missing = MagicMock(
        side_effect=stripe.InvalidRequestError(
            "No such payment_intent: 'pi_test'; a similar object exists in "
            "test mode, but a live mode key was used to make this request.",
            param="intent",
            code="resource_missing",
            http_status=404,
        )
    )
    return patch.object(stripe.PaymentIntent, "cancel", missing)


def _variant(category, name, price="20.00", stock=10):
    candle = Candle.objects.create(
        category=category, name=name, price=price, stock_qty=stock
    )
    return CandleVariant.objects.create(
        candle=candle, size="8 oz", price=price, stock_qty=stock, is_active=True
    )


def _order(user, lines):
    with patch(
        "orders.serializers.resolve_shipping_cost",
        return_value=(Decimal("8.00"), None),
    ):
        return build_order(
            user=user,
            lines=[{"variant_id": v.id, "quantity": q} for v, q in lines],
            shipping=ADDRESS,
        )


def _stock(*variants):
    return [CandleVariant.objects.get(pk=v.pk).stock_qty for v in variants]


@pytest.fixture
def welcome(db):
    return Offer.objects.create(
        title="Welcome 10%",
        kind=Offer.Kind.NEW_SHOPPER,
        discount_percent=10,
        apply_globally=True,
    )


@pytest.fixture
def two_variants(category):
    return _variant(category, "Amber"), _variant(category, "Cedar")


# ======================================================
# PART 2 — WELCOME OFFER
# ======================================================
@pytest.mark.django_db
class TestWelcomeOfferEligibility:
    @pytest.mark.parametrize(
        "status, keeps_offer",
        [
            (Order.Status.PENDING, True),  # unpaid attempt
            (Order.Status.CANCELED, True),
            (Order.Status.REFUNDED, True),  # never shipped — our cancellation
            (Order.Status.PAID, False),
            (Order.Status.SHIPPED, False),
            (Order.Status.COMPLETED, False),
        ],
    )
    def test_only_paid_and_shipped_orders_use_it_up(
        self, user, welcome, status, keeps_offer
    ):
        Order.objects.create(user=user, status=status)

        assert (get_welcome_offer(user) == welcome) is keeps_offer

    def test_second_attempt_keeps_the_discount_until_one_is_paid(
        self, user, welcome, category
    ):
        variant = _variant(category, "Amber", price="20.00")

        first = _order(user, [(variant, 1)])
        second = _order(user, [(variant, 1)])

        assert first.discount_amount == Decimal("2.00")
        assert second.discount_amount == Decimal("2.00")

        Order.objects.filter(pk=first.pk).update(status=Order.Status.PAID)
        third = _order(user, [(variant, 1)])

        assert third.discount_amount == Decimal("0.00")


# ======================================================
# PART 3 — STOCK GOES BACK
# ======================================================
@pytest.mark.django_db
class TestTransitionsReleaseStock:
    def test_cancelling_a_pending_order_restores_each_variant(self, user, two_variants):
        amber, cedar = two_variants
        order = _order(user, [(amber, 2), (cedar, 3)])
        assert _stock(amber, cedar) == [8, 7]

        order.transition_to(Order.Status.CANCELED)

        assert _stock(amber, cedar) == [10, 10]
        assert Order.objects.get(pk=order.pk).status == Order.Status.CANCELED

    def test_a_second_cancel_is_refused_and_restores_nothing(self, user, two_variants):
        amber, _ = two_variants
        order = _order(user, [(amber, 2)])
        order.transition_to(Order.Status.CANCELED)

        with pytest.raises(ValueError):
            order.transition_to(Order.Status.CANCELED)

        assert _stock(amber) == [10]

    def test_a_stale_copy_cannot_cancel_twice(self, user, two_variants):
        """Two requests holding the same order: the lock re-reads the row."""
        amber, _ = two_variants
        order = _order(user, [(amber, 2)])
        stale = Order.objects.get(pk=order.pk)

        order.transition_to(Order.Status.CANCELED)

        with pytest.raises(ValueError):
            stale.transition_to(Order.Status.CANCELED)

        assert _stock(amber) == [10]

    def test_refunding_a_paid_order_restores_stock(self, user, two_variants):
        amber, _ = two_variants
        order = _order(user, [(amber, 4)])
        order.transition_to(Order.Status.PAID)
        assert _stock(amber) == [6]

        order.transition_to(Order.Status.REFUNDED)

        assert _stock(amber) == [10]

    def test_a_shipped_order_cannot_be_refunded_and_keeps_its_stock(
        self, user, two_variants
    ):
        amber, _ = two_variants
        order = _order(user, [(amber, 4)])
        order.transition_to(Order.Status.PAID)
        order.transition_to(Order.Status.SHIPPED)

        with pytest.raises(ValueError):
            order.transition_to(Order.Status.REFUNDED)

        assert _stock(amber) == [6]

    def test_paying_does_not_touch_stock(self, user, two_variants):
        amber, _ = two_variants
        order = _order(user, [(amber, 4)])

        order.transition_to(Order.Status.PAID)

        assert _stock(amber) == [6]


@pytest.mark.django_db
class TestShopperCancel:
    def url(self, order):
        return f"/api/orders/{order.pk}/cancel/"

    def test_cancels_own_order_closes_intent_and_restores_stock(
        self, auth_client, user, two_variants
    ):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        Order.objects.filter(pk=order.pk).update(stripe_payment_intent_id="pi_123")

        with stripe_cancels() as cancel:
            response = auth_client.post(self.url(order))

        assert response.status_code == 200
        cancel.assert_called_once_with("pi_123")
        assert _stock(amber) == [10]
        assert Order.objects.get(pk=order.pk).status == Order.Status.CANCELED

    def test_order_without_an_intent_needs_no_stripe_call(
        self, auth_client, user, two_variants
    ):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])

        response = auth_client.post(self.url(order))  # no_stripe would fail on a call

        assert response.status_code == 200
        assert _stock(amber) == [10]

    def test_someone_elses_order_is_404(self, other_auth_client, user, two_variants):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])

        response = other_auth_client.post(self.url(order))

        assert response.status_code == 404
        assert _stock(amber) == [7]

    def test_a_paid_order_cannot_be_cancelled_here(self, auth_client, user, two_variants):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        order.transition_to(Order.Status.PAID)

        response = auth_client.post(self.url(order))

        assert response.status_code == 400
        assert _stock(amber) == [7]

    @pytest.mark.parametrize("intent_status", ["succeeded", "processing"])
    def test_payment_in_progress_is_409_and_nothing_changes(
        self, auth_client, user, two_variants, intent_status
    ):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        Order.objects.filter(pk=order.pk).update(stripe_payment_intent_id="pi_123")

        cancel, retrieve = stripe_refuses(intent_status)
        with cancel, retrieve:
            response = auth_client.post(self.url(order))

        assert response.status_code == 409
        assert _stock(amber) == [7]
        assert Order.objects.get(pk=order.pk).status == Order.Status.PENDING

    def test_already_cancelled_intent_still_lets_the_order_go(
        self, auth_client, user, two_variants
    ):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        Order.objects.filter(pk=order.pk).update(stripe_payment_intent_id="pi_123")

        cancel, retrieve = stripe_refuses("canceled")
        with cancel, retrieve:
            response = auth_client.post(self.url(order))

        assert response.status_code == 200
        assert _stock(amber) == [10]

    def test_intent_stripe_has_never_heard_of_still_lets_the_order_go(
        self, auth_client, user, two_variants
    ):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        Order.objects.filter(pk=order.pk).update(stripe_payment_intent_id="pi_test")

        # retrieve stays on no_stripe's tripwire: a 404 must not need a re-read.
        with stripe_has_no_such_intent() as cancel:
            response = auth_client.post(self.url(order))

        assert response.status_code == 200
        cancel.assert_called_once_with("pi_test")
        assert _stock(amber) == [10]
        assert Order.objects.get(pk=order.pk).status == Order.Status.CANCELED

    def test_stripe_unreachable_is_502_and_nothing_changes(
        self, auth_client, user, two_variants
    ):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        Order.objects.filter(pk=order.pk).update(stripe_payment_intent_id="pi_123")

        down = MagicMock(side_effect=stripe.APIConnectionError("network down"))
        with patch.object(stripe.PaymentIntent, "cancel", down):
            response = auth_client.post(self.url(order))

        assert response.status_code == 502
        assert _stock(amber) == [7]
        assert Order.objects.get(pk=order.pk).status == Order.Status.PENDING


@pytest.mark.django_db
def test_staff_cancel_goes_through_the_same_path(staff_client, user, two_variants):
    amber, _ = two_variants
    order = _order(user, [(amber, 3)])
    Order.objects.filter(pk=order.pk).update(stripe_payment_intent_id="pi_456")

    with stripe_cancels() as cancel:
        response = staff_client.patch(
            f"/api/orders/{order.pk}/status/", {"status": "canceled"}, format="json"
        )

    assert response.status_code == 200
    cancel.assert_called_once_with("pi_456")
    assert _stock(amber) == [10]


@pytest.mark.django_db
def test_staff_cancel_of_an_intent_stripe_lacks(staff_client, user, two_variants):
    amber, _ = two_variants
    order = _order(user, [(amber, 3)])
    Order.objects.filter(pk=order.pk).update(stripe_payment_intent_id="pi_test")

    with stripe_has_no_such_intent():
        response = staff_client.patch(
            f"/api/orders/{order.pk}/status/", {"status": "canceled"}, format="json"
        )

    assert response.status_code == 200
    assert _stock(amber) == [10]


def fake_stripe(missing=(), statuses=None):
    """Stripe as the expiry run sees it, per intent id.

    `missing` ids answer 404 resource_missing to both lookup and cancel;
    `statuses` maps an id to its status (default requires_payment_method).
    Succeeded or processing intents refuse cancellation, like the real API.
    Returns the (retrieve, cancel) mocks inside a combined context manager.
    """
    statuses = statuses or {}

    def not_found(intent_id):
        return stripe.InvalidRequestError(
            f"No such payment_intent: '{intent_id}'",
            param="intent",
            code="resource_missing",
            http_status=404,
        )

    def retrieve(intent_id):
        if intent_id in missing:
            raise not_found(intent_id)
        return SimpleNamespace(status=statuses.get(intent_id, "requires_payment_method"))

    def cancel(intent_id):
        if intent_id in missing:
            raise not_found(intent_id)
        if statuses.get(intent_id) in ("succeeded", "processing"):
            raise stripe.InvalidRequestError("unexpected state", param=None)
        return None

    retrieve_mock = MagicMock(side_effect=retrieve)
    cancel_mock = MagicMock(side_effect=cancel)

    class _Both:
        def __enter__(self):
            self._patches = [
                patch.object(stripe.PaymentIntent, "retrieve", retrieve_mock),
                patch.object(stripe.PaymentIntent, "cancel", cancel_mock),
            ]
            for p in self._patches:
                p.start()
            return retrieve_mock, cancel_mock

        def __exit__(self, *exc):
            for p in reversed(self._patches):
                p.stop()

    return _Both()


@pytest.mark.django_db
class TestExpirePendingOrders:
    def _age(self, order, hours):
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(hours=hours)
        )

    def _stale_order(self, user, variant, intent_id, qty=1):
        order = _order(user, [(variant, qty)])
        Order.objects.filter(pk=order.pk).update(stripe_payment_intent_id=intent_id)
        self._age(order, hours=3)
        return order

    def _run(self, *args):
        out = StringIO()
        call_command("expire_pending_orders", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def _statuses(self, *orders):
        return [Order.objects.get(pk=o.pk).status for o in orders]

    # --- ordinary runs -------------------------------------------------
    def test_old_unpaid_order_is_cancelled_and_restocked(self, user, two_variants):
        amber, _ = two_variants
        order = self._stale_order(user, amber, "pi_old", qty=3)

        with fake_stripe() as (_, cancel):
            output = self._run()

        cancel.assert_called_once_with("pi_old")
        assert _stock(amber) == [10]
        assert self._statuses(order) == [Order.Status.CANCELED]
        assert "cancelled 1" in output

    def test_recent_order_is_left_alone(self, user, two_variants):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        self._age(order, hours=1)

        self._run()

        assert _stock(amber) == [7]
        assert self._statuses(order) == [Order.Status.PENDING]

    def test_cutoff_is_configurable(self, user, two_variants):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        self._age(order, hours=1)

        self._run("--older-than", "30m")

        assert _stock(amber) == [10]

    def test_payment_in_progress_is_skipped(self, user, two_variants):
        amber, _ = two_variants
        order = self._stale_order(user, amber, "pi_busy", qty=3)

        with fake_stripe(statuses={"pi_busy": "processing"}):
            output = self._run()

        assert _stock(amber) == [7]
        assert self._statuses(order) == [Order.Status.PENDING]
        assert "left for the webhook" in output

    def test_order_without_intent_is_cancelled_without_stripe(self, user, two_variants):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        self._age(order, hours=3)

        self._run()  # no_stripe would fail on any call

        assert _stock(amber) == [10]

    def test_paid_orders_are_never_touched(self, user, two_variants):
        amber, _ = two_variants
        order = _order(user, [(amber, 3)])
        order.transition_to(Order.Status.PAID)
        self._age(order, hours=30)

        self._run()

        assert _stock(amber) == [7]
        assert self._statuses(order) == [Order.Status.PAID]

    def test_dry_run_changes_nothing_and_calls_no_stripe(self, user, two_variants):
        amber, _ = two_variants
        order = self._stale_order(user, amber, "pi_old", qty=3)

        output = self._run("--dry-run")  # no_stripe would fail on any call

        assert f"would cancel order #{order.pk}" in output
        assert _stock(amber) == [7]

    # --- intents Stripe doesn't have -----------------------------------
    def test_a_few_missing_intents_are_cancelled_not_retried_forever(
        self, user, two_variants
    ):
        """The local run that found this: two test-key intents queried with
        the live key come back 404, and were skipped on every run. Two is
        below the minimum sample, so the ratio guard doesn't apply."""
        amber, cedar = two_variants
        first = self._stale_order(user, amber, "pi_test_a", qty=3)
        second = self._stale_order(user, cedar, "pi_test_b", qty=2)

        with fake_stripe(missing={"pi_test_a", "pi_test_b"}):
            output = self._run()

        assert "cancelled 2, skipped 0, Stripe errors 0" in output
        assert _stock(amber, cedar) == [10, 10]
        assert self._statuses(first, second) == [Order.Status.CANCELED] * 2

        # The next scheduled run finds nothing left to do.
        assert "cancelled 0, skipped 0, Stripe errors 0" in self._run()

    def test_all_missing_looks_like_a_wrong_key_and_stops_before_any_change(
        self, user, category
    ):
        variants = [_variant(category, f"Candle {i}") for i in range(10)]
        orders = [
            self._stale_order(user, v, f"pi_other_account_{i}", qty=2)
            for i, v in enumerate(variants)
        ]
        missing = {f"pi_other_account_{i}" for i in range(10)}

        with fake_stripe(missing=missing) as (retrieve, cancel):
            with pytest.raises(CommandError) as stopped:
                self._run()

        assert "STOPPED: 10 of 10" in str(stopped.value)
        assert "No orders were cancelled" in str(stopped.value)
        assert retrieve.call_count == 10  # looked up, read-only
        cancel.assert_not_called()
        assert self._statuses(*orders) == [Order.Status.PENDING] * 10
        assert _stock(*variants) == [8] * 10

    def test_a_small_share_missing_among_real_intents_proceeds(
        self, user, category
    ):
        """Old test-mode orders mixed into a normal backlog: 2 of 20."""
        variants = [_variant(category, f"Candle {i}") for i in range(20)]
        orders = [
            self._stale_order(user, v, f"pi_{i}") for i, v in enumerate(variants)
        ]

        with fake_stripe(missing={"pi_3", "pi_11"}):
            output = self._run()

        assert "2 of 20 intents not found" in output
        assert "cancelled 20, skipped 0, Stripe errors 0" in output
        assert self._statuses(*orders) == [Order.Status.CANCELED] * 20

    def test_just_over_the_limit_stops(self, user, category):
        """3 of 5 is 60%: over the default 50%, at the minimum sample."""
        variants = [_variant(category, f"Candle {i}") for i in range(5)]
        orders = [
            self._stale_order(user, v, f"pi_{i}") for i, v in enumerate(variants)
        ]

        with fake_stripe(missing={"pi_0", "pi_1", "pi_2"}):
            with pytest.raises(CommandError, match="STOPPED: 3 of 5"):
                self._run()

        assert self._statuses(*orders) == [Order.Status.PENDING] * 5

    def test_the_limit_can_be_lifted_for_known_test_orders(self, user, category):
        variants = [_variant(category, f"Candle {i}") for i in range(6)]
        orders = [
            self._stale_order(user, v, f"pi_test_{i}") for i, v in enumerate(variants)
        ]

        with fake_stripe(missing={f"pi_test_{i}" for i in range(6)}):
            output = self._run("--max-missing-ratio", "1")

        assert "cancelled 6" in output
        assert self._statuses(*orders) == [Order.Status.CANCELED] * 6

    def test_unreachable_lookups_dont_count_towards_the_ratio(self, user, category):
        """Network trouble says nothing about the key: 5 lookups fail, 1 is
        missing, 1 is fine — 1 of 2 counted, below the minimum sample."""
        variants = [_variant(category, f"Candle {i}") for i in range(7)]
        for i, v in enumerate(variants):
            self._stale_order(user, v, f"pi_{i}")

        def retrieve(intent_id):
            if intent_id == "pi_0":
                return SimpleNamespace(status="requires_payment_method")
            if intent_id == "pi_1":
                raise stripe.InvalidRequestError(
                    "No such payment_intent", param="intent",
                    code="resource_missing", http_status=404,
                )
            raise stripe.APIConnectionError("network down")

        def cancel(intent_id):
            if intent_id in ("pi_0",):
                return None
            return retrieve(intent_id)

        with patch.object(stripe.PaymentIntent, "retrieve", MagicMock(side_effect=retrieve)), \
                patch.object(stripe.PaymentIntent, "cancel", MagicMock(side_effect=cancel)):
            output = self._run()

        # pi_0 cancelled, pi_1 missing so released, pi_2..pi_6 left for next run.
        assert "cancelled 2, skipped 0, Stripe errors 5" in output

    def test_a_stopped_run_fails_the_process_like_cron_sees_it(
        self, user, category, capsys
    ):
        """Through manage.py's own entry point, not call_command: the stop has
        to surface as exit status 1 and a line on stderr, which is what a
        Railway cron run shows."""
        from orders.management.commands.expire_pending_orders import Command

        variants = [_variant(category, f"Candle {i}") for i in range(5)]
        for i, v in enumerate(variants):
            self._stale_order(user, v, f"pi_gone_{i}")

        with fake_stripe(missing={f"pi_gone_{i}" for i in range(5)}):
            with pytest.raises(SystemExit) as exited:
                Command().run_from_argv(["manage.py", "expire_pending_orders"])

        assert exited.value.code == 1
        assert "CommandError: STOPPED: 5 of 5" in capsys.readouterr().err
