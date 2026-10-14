import hashlib
import hmac
import json
import time
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe
from django.core import mail

from orders.models import Order, PaymentIncident


WEBHOOK_URL = "/api/orders/webhook/"
TEST_SECRET = "whsec_test_dummy"


def _sign(payload: str, secret: str = TEST_SECRET) -> str:
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload}"
    sig = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


@pytest.mark.django_db
class TestStripeWebhookSecretGuard:
    def test_returns_500_when_secret_not_configured(self, api_client, settings):
        settings.STRIPE_WEBHOOK_SECRET = ""

        response = api_client.post(
            WEBHOOK_URL,
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=whatever",
        )

        assert response.status_code == 500

    def test_rejects_bad_signature_when_secret_is_configured(self, api_client, settings):
        settings.STRIPE_WEBHOOK_SECRET = "whsec_test_dummy"

        response = api_client.post(
            WEBHOOK_URL,
            data=b'{"type": "payment_intent.succeeded"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=not-a-real-signature",
        )

        assert response.status_code == 400


@pytest.mark.django_db
class TestStripeWebhookMetadataGuard:
    def test_event_with_no_metadata_key_is_ignored_not_500(self, api_client, settings):
        # Regression test: data["metadata"] used to be accessed with plain
        # bracket indexing, so an event with no "metadata" key at all (e.g.
        # a payment_intent type this app didn't create) raised an uncaught
        # KeyError -> 500 instead of being safely ignored.
        settings.STRIPE_WEBHOOK_SECRET = TEST_SECRET

        payload = (
            '{"id": "evt_1", "type": "payment_intent.succeeded", '
            '"data": {"object": {"id": "pi_no_metadata"}}}'
        )

        response = api_client.post(
            WEBHOOK_URL,
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=_sign(payload),
        )

        assert response.status_code == 200


class TestCentAmountRounding:
    """Mirrors the exact expression CreatePaymentIntentView uses to convert
    order.total_amount into the integer cent amount Stripe's API expects -
    plain Decimal math, no DB/HTTP needed."""

    @staticmethod
    def _to_cents(amount: str) -> int:
        return int(
            (Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )

    def test_exact_cent_amounts_unaffected(self):
        assert self._to_cents("24.00") == 2400
        assert self._to_cents("0.50") == 50

    def test_rounds_instead_of_truncating(self):
        # int(Decimal("19.995") * 100) truncates to 1999; this should round
        # to the nearest cent (2000) instead.
        assert self._to_cents("19.995") == 2000
        assert self._to_cents("0.005") == 1


# ======================================================
# payment_intent.succeeded
# ======================================================
def _succeeded(api_client, order, intent_id="pi_paid", amount=4250, currency="usd"):
    payload = json.dumps(
        {
            "id": "evt_paid",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": intent_id,
                    "amount_received": amount,
                    "currency": currency,
                    "metadata": {"order_id": str(order.pk)},
                }
            },
        }
    )
    return api_client.post(
        WEBHOOK_URL,
        data=payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_sign(payload),
    )


def _refund_ok(refund_id="re_123"):
    return patch.object(
        stripe.Refund, "create", MagicMock(return_value=SimpleNamespace(id=refund_id))
    )


def _refund_raises(error):
    return patch.object(stripe.Refund, "create", MagicMock(side_effect=error))


def _cancel_ok():
    return patch.object(stripe.PaymentIntent, "cancel", MagicMock())


@pytest.fixture
def webhook_secret(settings):
    settings.STRIPE_WEBHOOK_SECRET = TEST_SECRET


@pytest.mark.django_db
@pytest.mark.usefixtures("webhook_secret")
class TestStripeWebhookPaymentSucceeded:
    def _order(self, user, status=Order.Status.PENDING, intent_id="pi_paid"):
        # 42.50, matching the 4250 cents _succeeded reports as received.
        return Order.objects.create(
            user=user,
            status=status,
            stripe_payment_intent_id=intent_id,
            total_amount=Decimal("42.50"),
            currency="usd",
        )

    def test_pending_becomes_paid_and_no_email_is_sent(self, api_client, user):
        # Confirmation emails are sent by hand; the automatic one rendered
        # blank. A successful payment changes the status and nothing else.
        order = self._order(user)

        with _refund_ok() as refund:
            response = _succeeded(api_client, order)

        assert response.status_code == 200
        assert Order.objects.get(pk=order.pk).status == Order.Status.PAID
        refund.assert_not_called()
        assert mail.outbox == []

    @pytest.mark.parametrize(
        "status", [Order.Status.PAID, Order.Status.SHIPPED, Order.Status.COMPLETED]
    )
    def test_a_redelivery_never_moves_an_order_back(self, api_client, user, status):
        order = self._order(user, status=status)

        with _refund_ok() as refund:
            response = _succeeded(api_client, order)

        assert response.status_code == 200
        assert Order.objects.get(pk=order.pk).status == status
        refund.assert_not_called()
        assert PaymentIncident.objects.count() == 0
        assert mail.outbox == []

    def test_payment_on_a_cancelled_order_is_refunded_and_reported(
        self, api_client, user, settings
    ):
        order = self._order(user, status=Order.Status.CANCELED)

        with _refund_ok("re_cancelled") as refund:
            response = _succeeded(api_client, order, amount=4250)

        assert response.status_code == 200
        refund.assert_called_once_with(
            payment_intent="pi_paid",
            metadata={"order_id": str(order.pk), "reason": "paid_after_cancel"},
            idempotency_key="unfulfillable-pi_paid",
        )

        assert Order.objects.get(pk=order.pk).status == Order.Status.CANCELED

        incident = PaymentIncident.objects.get()
        assert incident.order == order
        assert incident.kind == PaymentIncident.Kind.PAID_AFTER_CANCEL
        assert incident.outcome == PaymentIncident.Outcome.REFUNDED
        assert incident.stripe_refund_id == "re_cancelled"
        assert incident.amount == Decimal("42.50")
        assert incident.resolved_at is None

        assert len(mail.outbox) == 1
        alert = mail.outbox[0]
        assert alert.to == [settings.SUPPORT_EMAIL]
        assert f"Refunded 42.50 USD paid on canceled order #{order.pk}" in alert.subject
        assert "re_cancelled" in alert.body

    def test_the_same_event_again_refunds_and_alerts_once(self, api_client, user):
        order = self._order(user, status=Order.Status.CANCELED)

        with _refund_ok() as refund:
            _succeeded(api_client, order)
            response = _succeeded(api_client, order)

        assert response.status_code == 200
        assert refund.call_count == 1
        assert PaymentIncident.objects.count() == 1
        assert len(mail.outbox) == 1

    def test_a_failed_refund_says_so_once_and_retries_until_it_works(
        self, api_client, user
    ):
        order = self._order(user, status=Order.Status.CANCELED)
        outage = stripe.APIConnectionError("network down")

        # Stripe unreachable: 500 so Stripe redelivers; one alert, not two.
        with _refund_raises(outage):
            first = _succeeded(api_client, order)
            second = _succeeded(api_client, order)

        assert first.status_code == second.status_code == 500
        incident = PaymentIncident.objects.get()
        assert incident.outcome == PaymentIncident.Outcome.REFUND_FAILED
        assert "network down" in incident.detail
        assert len(mail.outbox) == 1
        assert "ACTION NEEDED" in mail.outbox[0].subject

        # Stripe is back: the next redelivery refunds, and says so.
        with _refund_ok("re_late"):
            third = _succeeded(api_client, order)

        assert third.status_code == 200
        incident.refresh_from_db()
        assert incident.outcome == PaymentIncident.Outcome.REFUNDED
        assert incident.stripe_refund_id == "re_late"
        assert len(mail.outbox) == 2
        assert "Refunded" in mail.outbox[1].subject

    def test_payment_on_a_refunded_order_is_refunded_too(self, api_client, user):
        # REFUNDED as a status moves no money: if Stripe still took this
        # payment, the refund here is what actually returns it.
        order = self._order(user, status=Order.Status.REFUNDED)

        with _refund_ok("re_again"):
            response = _succeeded(api_client, order)

        assert response.status_code == 200
        incident = PaymentIncident.objects.get()
        assert incident.kind == PaymentIncident.Kind.PAID_AFTER_REFUND
        assert incident.outcome == PaymentIncident.Outcome.REFUNDED
        assert Order.objects.get(pk=order.pk).status == Order.Status.REFUNDED
        assert len(mail.outbox) == 1

    def test_already_refunded_at_stripe_is_not_an_incident(self, api_client, user):
        # A redelivery after someone refunded by hand in the dashboard.
        order = self._order(user, status=Order.Status.REFUNDED)
        already = stripe.InvalidRequestError(
            "Charge has already been refunded.",
            param=None,
            code="charge_already_refunded",
        )

        with _refund_raises(already):
            response = _succeeded(api_client, order)

        assert response.status_code == 200
        assert PaymentIncident.objects.count() == 0
        assert mail.outbox == []

    # --------------------------------------------------------------
    # A payment on an intent the order has moved on from
    # --------------------------------------------------------------
    # Checkout replaces an order's intent when it can't ask Stripe about the
    # old one, or the old one is mid-payment. A form still showing the old
    # intent can then be paid. That money must never be dropped: the first
    # payment of the right amount pays the order, whichever intent it was on.

    def test_a_payment_on_a_replaced_intent_pays_the_order(self, api_client, user, caplog):
        order = self._order(user, intent_id="pi_current")

        with _refund_ok() as refund, _cancel_ok() as cancel, caplog.at_level("INFO"):
            response = _succeeded(api_client, order, intent_id="pi_old")

        assert response.status_code == 200
        refund.assert_not_called()

        # The order now uses the intent that was paid, and the one it had is
        # cancelled so it can't take a second payment.
        order.refresh_from_db()
        assert order.status == Order.Status.PAID
        assert order.stripe_payment_intent_id == "pi_old"
        cancel.assert_called_once_with("pi_current")

        # Not an incident: an info line naming both intents, no alert.
        assert PaymentIncident.objects.count() == 0
        assert mail.outbox == []
        assert any(
            r.levelname == "INFO" and "pi_old" in r.getMessage() and "pi_current" in r.getMessage()
            for r in caplog.records
        )
        assert not any(r.levelno >= 30 for r in caplog.records)

    def test_a_replaced_intent_paid_is_settled_even_if_the_other_cant_be_cancelled(
        self, api_client, user
    ):
        order = self._order(user, intent_id="pi_current")
        outage = stripe.APIConnectionError("network down")

        with _refund_ok() as refund, patch.object(
            stripe.PaymentIntent, "cancel", MagicMock(side_effect=outage)
        ):
            response = _succeeded(api_client, order, intent_id="pi_old")

        assert response.status_code == 200
        refund.assert_not_called()
        order.refresh_from_db()
        assert order.status == Order.Status.PAID
        assert order.stripe_payment_intent_id == "pi_old"

    def test_a_replaced_intent_paid_redelivered_changes_nothing(self, api_client, user):
        order = self._order(user, intent_id="pi_current")

        with _refund_ok() as refund, _cancel_ok() as cancel:
            _succeeded(api_client, order, intent_id="pi_old")
            response = _succeeded(api_client, order, intent_id="pi_old")

        assert response.status_code == 200
        refund.assert_not_called()
        cancel.assert_called_once()
        order.refresh_from_db()
        assert order.status == Order.Status.PAID
        assert order.stripe_payment_intent_id == "pi_old"

    def test_a_payment_on_the_other_intent_afterwards_is_refunded_and_reported(
        self, api_client, user, settings
    ):
        # The old form won; the cancel of pi_current came too late (or
        # failed) and it was paid as well. The order is paid once.
        order = self._order(user, intent_id="pi_current")

        with _cancel_ok():
            _succeeded(api_client, order, intent_id="pi_old")

        with _refund_ok("re_second") as refund:
            response = _succeeded(api_client, order, intent_id="pi_current")

        assert response.status_code == 200
        refund.assert_called_once_with(
            payment_intent="pi_current",
            metadata={"order_id": str(order.pk), "reason": "paid_on_replaced_intent"},
            idempotency_key="unfulfillable-pi_current",
        )

        order.refresh_from_db()
        assert order.status == Order.Status.PAID
        assert order.stripe_payment_intent_id == "pi_old"

        incident = PaymentIncident.objects.get()
        assert incident.kind == PaymentIncident.Kind.PAID_ON_REPLACED_INTENT
        assert incident.outcome == PaymentIncident.Outcome.REFUNDED
        assert incident.stripe_payment_intent_id == "pi_current"
        assert incident.stripe_refund_id == "re_second"

        [alert] = mail.outbox
        assert alert.to == [settings.SUPPORT_EMAIL]
        assert "pi_old" in alert.body and "pi_current" in alert.body
        assert "this payment was not counted" in alert.body

    @pytest.mark.parametrize(
        "status", [Order.Status.PAID, Order.Status.SHIPPED, Order.Status.COMPLETED]
    )
    def test_a_replaced_intent_paid_after_the_order_was_paid_is_refunded(
        self, api_client, user, settings, status
    ):
        order = self._order(user, status=status, intent_id="pi_current")

        with _refund_ok("re_old") as refund, _cancel_ok() as cancel:
            response = _succeeded(api_client, order, intent_id="pi_old")

        assert response.status_code == 200
        refund.assert_called_once_with(
            payment_intent="pi_old",
            metadata={"order_id": str(order.pk), "reason": "paid_on_replaced_intent"},
            idempotency_key="unfulfillable-pi_old",
        )
        cancel.assert_not_called()

        # The order is untouched: still on its current intent, same status.
        order.refresh_from_db()
        assert order.status == status
        assert order.stripe_payment_intent_id == "pi_current"

        incident = PaymentIncident.objects.get()
        assert incident.kind == PaymentIncident.Kind.PAID_ON_REPLACED_INTENT
        assert incident.outcome == PaymentIncident.Outcome.REFUNDED
        assert incident.stripe_payment_intent_id == "pi_old"
        assert incident.amount == Decimal("42.50")

        [alert] = mail.outbox
        assert alert.to == [settings.SUPPORT_EMAIL]
        assert f"order #{order.pk}" in alert.subject
        assert "pi_old" in alert.body and "pi_current" in alert.body
        assert "stock has already been returned" not in alert.body

    def test_a_replaced_intent_for_the_wrong_amount_is_refunded_and_reported(
        self, api_client, user
    ):
        # The amount check is the gate: an old form priced before the shopper
        # changed shipping doesn't pay the order, whichever intent it's on.
        order = self._order(user, intent_id="pi_current")

        with _refund_ok() as refund, _cancel_ok() as cancel:
            response = _succeeded(api_client, order, intent_id="pi_old", amount=3900)

        assert response.status_code == 200
        refund.assert_called_once()
        assert refund.call_args.kwargs["payment_intent"] == "pi_old"
        assert refund.call_args.kwargs["metadata"]["reason"] == "amount_mismatch"
        cancel.assert_not_called()

        order.refresh_from_db()
        assert order.status == Order.Status.PENDING
        assert order.stripe_payment_intent_id == "pi_current"

        incident = PaymentIncident.objects.get()
        assert incident.kind == PaymentIncident.Kind.AMOUNT_MISMATCH
        assert len(mail.outbox) == 1

    @pytest.mark.parametrize(
        "status, kind",
        [
            (Order.Status.CANCELED, PaymentIncident.Kind.PAID_AFTER_CANCEL),
            (Order.Status.REFUNDED, PaymentIncident.Kind.PAID_AFTER_REFUND),
        ],
    )
    def test_a_replaced_intent_on_a_closed_order_says_what_closed_it(
        self, api_client, user, status, kind
    ):
        order = self._order(user, status=status, intent_id="pi_current")

        with _refund_ok():
            response = _succeeded(api_client, order, intent_id="pi_old")

        assert response.status_code == 200
        assert PaymentIncident.objects.get().kind == kind

    def test_a_replaced_intent_redelivered_refunds_and_alerts_once(self, api_client, user):
        order = self._order(user, status=Order.Status.PAID, intent_id="pi_current")

        with _refund_ok() as refund:
            _succeeded(api_client, order, intent_id="pi_old")
            response = _succeeded(api_client, order, intent_id="pi_old")

        assert response.status_code == 200
        assert refund.call_count == 1
        assert PaymentIncident.objects.count() == 1
        assert len(mail.outbox) == 1

    def test_an_order_that_does_not_exist_is_logged_as_an_error(
        self, api_client, user, caplog
    ):
        """No order to hang an incident on: the log is all there can be, so
        it is an error a person will see, not a warning."""
        missing = SimpleNamespace(pk=999_999)

        with _refund_ok() as refund, caplog.at_level("ERROR"):
            response = _succeeded(api_client, missing, intent_id="pi_orphan")

        assert response.status_code == 200
        refund.assert_not_called()
        assert any(
            "pi_orphan" in r.getMessage() and r.levelname == "ERROR" for r in caplog.records
        )

    # --------------------------------------------------------------
    # Amount and currency
    # --------------------------------------------------------------
    @pytest.mark.parametrize(
        "amount, currency",
        [(4249, "usd"), (4251, "usd"), (0, "usd"), (4250, "eur")],
        ids=["a-cent-short", "a-cent-over", "nothing", "other-currency"],
    )
    def test_a_payment_that_does_not_match_the_order_is_not_counted(
        self, api_client, user, amount, currency
    ):
        order = self._order(user)

        with _refund_ok("re_mismatch") as refund:
            response = _succeeded(api_client, order, amount=amount, currency=currency)

        assert response.status_code == 200
        assert Order.objects.get(pk=order.pk).status == Order.Status.PENDING
        refund.assert_called_once()
        assert refund.call_args.kwargs["metadata"]["reason"] == "amount_mismatch"

        incident = PaymentIncident.objects.get()
        assert incident.kind == PaymentIncident.Kind.AMOUNT_MISMATCH
        assert incident.outcome == PaymentIncident.Outcome.REFUNDED
        assert "42.50 USD" in incident.detail

        [alert] = mail.outbox
        assert "42.50 USD" in alert.body

    def test_a_mismatch_redelivered_refunds_once(self, api_client, user):
        order = self._order(user)

        with _refund_ok() as refund:
            _succeeded(api_client, order, amount=4000)
            response = _succeeded(api_client, order, amount=4000)

        assert response.status_code == 200
        assert refund.call_count == 1
        assert len(mail.outbox) == 1

    def test_the_currency_is_compared_without_case(self, api_client, user):
        order = self._order(user)

        with _refund_ok() as refund:
            response = _succeeded(api_client, order, currency="USD")

        assert response.status_code == 200
        assert Order.objects.get(pk=order.pk).status == Order.Status.PAID
        refund.assert_not_called()


@pytest.mark.django_db
class TestPaymentIncidentAdmin:
    URL = "/admin/orders/paymentincident/"

    @pytest.fixture
    def admin_client(self, client):
        from accounts.models import User

        boss = User.objects.create_superuser(email="boss@example.com", password="pw-12345!")
        client.force_login(boss)
        return client

    def _incident(self, user, intent_id, resolved=False):
        from django.utils import timezone

        order = Order.objects.create(user=user, status=Order.Status.CANCELED)
        return PaymentIncident.objects.create(
            order=order,
            kind=PaymentIncident.Kind.PAID_AFTER_CANCEL,
            outcome=PaymentIncident.Outcome.REFUNDED,
            stripe_payment_intent_id=intent_id,
            stripe_refund_id=f"re_{intent_id}",
            amount=Decimal("10.00"),
            resolved_at=timezone.now() if resolved else None,
        )

    def test_list_opens_on_the_unresolved_ones(self, admin_client, user):
        self._incident(user, "pi_open")
        self._incident(user, "pi_done", resolved=True)

        page = admin_client.get(self.URL).content.decode()

        assert "re_pi_open" in page
        assert "re_pi_done" not in page

    def test_mark_resolved_takes_it_off_the_list(self, admin_client, user):
        incident = self._incident(user, "pi_open")

        admin_client.post(
            self.URL,
            {"action": "mark_resolved", "_selected_action": [incident.pk]},
        )

        incident.refresh_from_db()
        assert incident.resolved_at is not None
        assert "re_pi_open" not in admin_client.get(self.URL).content.decode()

    def test_shown_on_the_order_page(self, admin_client, user):
        incident = self._incident(user, "pi_open")

        page = admin_client.get(
            f"/admin/orders/order/{incident.order_id}/change/"
        ).content.decode()

        assert "re_pi_open" in page
