"""Refunds are made in Stripe; the order follows.

charge.refunded records how much has gone back. A full refund moves the
order to REFUNDED: from PAID that puts the stock back, after shipping it
doesn't (a lit candle can't be sold again). A partial refund changes
neither status nor stock. A refund of a payment the order doesn't count —
our own automatic refunds after cancel, on a replaced intent, or for the
wrong amount — never touches the order. The staff endpoint can't mark an
order refunded; the admin shows what went back, lets staff put a refunded
candle back on the shelf before shipping, and reports net revenue.
charge.dispute.created alerts a person.

Events are signed with a test secret; nothing reaches Stripe.
"""

import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import patch

import pytest

from candles.models import Candle, CandleVariant
from django.core import mail

from orders.models import Order, OrderItem, PaymentIncident
from orders.serializers import build_order

WEBHOOK_URL = "/api/orders/webhook/"
SECRET = "whsec_test_refunds"

ADDRESS = {
    "full_name": "Jane Doe", "line1": "1 Main St", "line2": "", "city": "Brooklyn",
    "state": "NY", "postal_code": "11201", "country": "US", "phone": "",
}


@pytest.fixture(autouse=True)
def webhook_secret(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRET


@pytest.fixture
def variant(db, category):
    candle = Candle.objects.create(category=category, name="Mango Island", stock_qty=10)
    return CandleVariant.objects.create(
        candle=candle, size="11.3 oz", price="20.00", stock_qty=10, is_active=True
    )


def _order(user, variant, status, intent_id="pi_paid", quantity=3):
    """A real order: stock reserved by build_order, then moved to `status`
    the way the shop moves it."""
    with patch("orders.serializers.resolve_shipping_cost", return_value=(Decimal("7.50"), None)):
        order = build_order(
            user=user,
            lines=[{"variant_id": variant.id, "quantity": quantity}],
            shipping=ADDRESS,
        )
    order.stripe_payment_intent_id = intent_id
    order.save(update_fields=["stripe_payment_intent_id"])

    path = {
        Order.Status.PENDING: [],
        Order.Status.PAID: [Order.Status.PAID],
        Order.Status.SHIPPED: [Order.Status.PAID, Order.Status.SHIPPED],
        Order.Status.COMPLETED: [Order.Status.PAID, Order.Status.SHIPPED, Order.Status.COMPLETED],
        Order.Status.REFUNDED: [Order.Status.PAID, Order.Status.REFUNDED],
        Order.Status.CANCELED: [Order.Status.CANCELED],
    }[status]
    for step in path:
        order.transition_to(step)

    return order


def _refunded(client, intent_id="pi_paid", captured=6750, refunded_amount=6750, full=True):
    """charge.refunded as Stripe sends it: the Charge, with cumulative
    amount_refunded and `refunded` true once nothing is left. No order_id
    metadata — charges don't reliably carry the intent's."""
    payload = json.dumps(
        {
            "id": "evt_refund",
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": "ch_1",
                    "object": "charge",
                    "payment_intent": intent_id,
                    "amount_captured": captured,
                    "amount_refunded": refunded_amount,
                    "refunded": full,
                    "currency": "usd",
                    "metadata": {},
                }
            },
        }
    )
    timestamp = int(time.time())
    signature = hmac.new(
        SECRET.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256
    ).hexdigest()
    return client.post(
        WEBHOOK_URL,
        data=payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={signature}",
    )


def _state(order, variant):
    order.refresh_from_db()
    variant.refresh_from_db()
    return order.status, variant.stock_qty


def _signed(client, payload):
    timestamp = int(time.time())
    signature = hmac.new(
        SECRET.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256
    ).hexdigest()
    return client.post(
        WEBHOOK_URL,
        data=payload,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=f"t={timestamp},v1={signature}",
    )


@pytest.mark.django_db
class TestFullRefund:
    def test_a_paid_order_becomes_refunded_and_its_stock_comes_back(
        self, api_client, user, variant
    ):
        order = _order(user, variant, Order.Status.PAID)
        assert variant.__class__.objects.get(pk=variant.pk).stock_qty == 7

        response = _refunded(api_client)

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.REFUNDED, 10)
        assert order.refunded_amount == order.total_amount == Decimal("67.50")

    @pytest.mark.parametrize("status", [Order.Status.SHIPPED, Order.Status.COMPLETED])
    def test_after_shipping_it_is_refunded_but_no_stock_comes_back(
        self, api_client, user, variant, status
    ):
        """A return: a candle that has been lit can't be sold again."""
        order = _order(user, variant, status)

        response = _refunded(api_client)

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.REFUNDED, 7)
        assert order.refunded_amount == Decimal("67.50")

    def test_units_already_returned_by_hand_are_not_returned_again(
        self, api_client, user, variant, admin_client
    ):
        order = _order(user, variant, Order.Status.PAID)
        item = order.items.get()
        _return_to_stock(admin_client, item)  # one candle of three: stock 8

        response = _refunded(api_client)

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.REFUNDED, 10)

    def test_the_same_event_twice_returns_the_stock_once(self, api_client, user, variant):
        order = _order(user, variant, Order.Status.PAID)

        _refunded(api_client)
        response = _refunded(api_client)

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.REFUNDED, 10)

    def test_partial_refunds_that_add_up_to_everything_refund_the_order(
        self, api_client, user, variant
    ):
        order = _order(user, variant, Order.Status.PAID)

        _refunded(api_client, refunded_amount=750, full=False)
        response = _refunded(api_client, refunded_amount=6750, full=True)

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.REFUNDED, 10)


@pytest.mark.django_db
class TestPartialRefund:
    def test_it_is_recorded_and_nothing_else_changes(self, api_client, user, variant):
        """Just the shipping back: the candles still need sending."""
        order = _order(user, variant, Order.Status.PAID)

        response = _refunded(api_client, refunded_amount=750, full=False)

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.PAID, 7)
        assert order.refunded_amount == Decimal("7.50")

    def test_after_shipping_too(self, api_client, user, variant):
        order = _order(user, variant, Order.Status.SHIPPED)

        _refunded(api_client, refunded_amount=2000, full=False)

        assert _state(order, variant) == (Order.Status.SHIPPED, 7)
        assert order.refunded_amount == Decimal("20.00")

    def test_an_older_event_arriving_late_never_lowers_it(self, api_client, user, variant):
        order = _order(user, variant, Order.Status.PAID)

        _refunded(api_client, refunded_amount=2750, full=False)
        _refunded(api_client, refunded_amount=750, full=False)

        order.refresh_from_db()
        assert order.refunded_amount == Decimal("27.50")


@pytest.mark.django_db
class TestLeftAlone:
    def test_already_refunded_is_a_redelivery(self, api_client, user, variant):
        order = _order(user, variant, Order.Status.REFUNDED)  # stock already back: 10

        response = _refunded(api_client)

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.REFUNDED, 10)

    def test_never_paid_is_left_pending(self, api_client, user, variant):
        """Our own refund of a wrong-amount payment on the current intent:
        the order stays payable and keeps its stock."""
        order = _order(user, variant, Order.Status.PENDING)

        response = _refunded(api_client)

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.PENDING, 7)
        assert order.refunded_amount == 0

    def test_cancelled_is_left_cancelled(self, api_client, user, variant):
        """Our own refund of a payment after cancel."""
        order = _order(user, variant, Order.Status.CANCELED)

        response = _refunded(api_client)

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.CANCELED, 10)
        assert order.refunded_amount == 0

    def test_refunding_a_replaced_intent_does_not_touch_the_paid_order(
        self, api_client, user, variant
    ):
        """Our own refund of a stray payment on an intent the order replaced:
        the order is paid with a different one and must stay PAID."""
        order = _order(user, variant, Order.Status.PAID, intent_id="pi_current")
        PaymentIncident.objects.create(
            order=order, stripe_payment_intent_id="pi_old",
            kind=PaymentIncident.Kind.PAID_ON_REPLACED_INTENT,
            outcome=PaymentIncident.Outcome.REFUNDED, amount=Decimal("67.50"),
        )

        response = _refunded(api_client, intent_id="pi_old")

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.PAID, 7)
        assert order.refunded_amount == 0

    def test_a_charge_that_is_not_ours_is_acknowledged(self, api_client, user, variant):
        response = _refunded(api_client, intent_id="pi_someone_else")

        assert response.status_code == 200

    def test_a_charge_with_no_payment_intent_is_acknowledged(self, api_client):
        response = _refunded(api_client, intent_id=None)

        assert response.status_code == 200


def _return_to_stock(admin_client, *items):
    return admin_client.post(
        "/admin/orders/orderitem/",
        {"action": "return_one_to_stock", "_selected_action": [i.pk for i in items]},
        follow=True,
    )


@pytest.mark.django_db
class TestStaffCannotMarkRefunded:
    URL = "/api/orders/{}/status/"

    def test_the_endpoint_refuses_and_says_where_to_refund(
        self, staff_client, user, variant
    ):
        order = _order(user, variant, Order.Status.PAID)

        response = staff_client.patch(self.URL.format(order.pk), {"status": "refunded"}, format="json")

        assert response.status_code == 400
        assert "Stripe dashboard" in response.json()["status"]
        assert _state(order, variant) == (Order.Status.PAID, 7)

    def test_other_moves_still_work(self, staff_client, user, variant):
        order = _order(user, variant, Order.Status.PAID)

        response = staff_client.patch(self.URL.format(order.pk), {"status": "shipped"}, format="json")

        assert response.status_code == 200
        assert _state(order, variant) == (Order.Status.SHIPPED, 7)


@pytest.mark.django_db
class TestReturnItemsToStock:
    def test_one_unit_per_run_never_more_than_the_line_holds(self, admin_client, user, variant):
        order = _order(user, variant, Order.Status.PAID)
        item = order.items.get()

        for _ in range(4):
            _return_to_stock(admin_client, item)

        item.refresh_from_db()
        assert item.restocked_quantity == 3
        assert _state(order, variant) == (Order.Status.PAID, 10)

    @pytest.mark.parametrize(
        "status", [Order.Status.PENDING, Order.Status.SHIPPED, Order.Status.COMPLETED,
                   Order.Status.REFUNDED, Order.Status.CANCELED],
    )
    def test_only_before_shipping(self, admin_client, user, variant, status):
        order = _order(user, variant, status)
        stock = variant.__class__.objects.get(pk=variant.pk).stock_qty

        response = _return_to_stock(admin_client, order.items.get())

        assert _state(order, variant) == (status, stock)
        assert OrderItem.objects.get(order=order).restocked_quantity == 0
        assert "not returned" in response.content.decode()


@pytest.mark.django_db
class TestAdmin:
    def test_the_order_list_shows_and_filters_partial_refunds(self, admin_client, user, variant):
        partly = _order(user, variant, Order.Status.PAID, intent_id="pi_a", quantity=1)
        whole = _order(user, variant, Order.Status.PAID, intent_id="pi_b", quantity=1)
        Order.objects.filter(pk=partly.pk).update(refunded_amount=Decimal("7.50"))
        Order.objects.filter(pk=whole.pk).update(status=Order.Status.REFUNDED)

        page = admin_client.get("/admin/orders/order/?refunds=partly").content.decode()

        assert "7.50 USD of 27.50" in page
        assert f"/admin/orders/order/{partly.pk}/change/" in page
        assert f"/admin/orders/order/{whole.pk}/change/" not in page

    def test_the_order_page_links_to_stripe_and_to_restocking(self, admin_client, user, variant):
        order = _order(user, variant, Order.Status.PAID)

        page = admin_client.get(f"/admin/orders/order/{order.pk}/change/").content.decode()

        assert "Refunded so far: 0.00 USD of 67.50 USD" in page
        assert "dashboard.stripe.com" in page and "pi_paid" in page
        assert f"order__id__exact={order.pk}" in page
        assert 'name="refunded_amount"' not in page  # shown, not editable

    def test_reports_count_paid_money_net_of_refunds(self, admin_client, user, variant):
        _order(user, variant, Order.Status.PENDING, intent_id="pi_1", quantity=1)  # 27.50, unpaid
        _order(user, variant, Order.Status.CANCELED, intent_id="pi_2", quantity=1)  # 27.50, unpaid
        partly = _order(user, variant, Order.Status.SHIPPED, intent_id="pi_3", quantity=3)  # 67.50
        Order.objects.filter(pk=partly.pk).update(refunded_amount=Decimal("7.50"))
        _order(user, variant, Order.Status.REFUNDED, intent_id="pi_4", quantity=1)  # 27.50, all back

        page = admin_client.get("/admin/orders/order/reports/").content.decode()

        assert "<b>Paid orders:</b> 2" in page
        assert "<b>Charged:</b> 95.00" in page
        assert "<b>Refunded:</b> 35.00" in page
        assert "<b>Revenue:</b> 60.00" in page
        # By product: only the shipped order's three candles at 20.00.
        assert "<td>Mango Island</td><td>3</td><td>60.00</td>" in page


@pytest.mark.django_db
class TestDisputes:
    def _dispute(self, client, intent_id="pi_paid"):
        return _signed(
            client,
            json.dumps(
                {
                    "id": "evt_dispute",
                    "type": "charge.dispute.created",
                    "data": {
                        "object": {
                            "id": "dp_1", "object": "dispute", "charge": "ch_1",
                            "payment_intent": intent_id, "amount": 6750, "currency": "usd",
                            "reason": "fraudulent",
                            "evidence_details": {"due_by": 1767225600},
                        }
                    },
                }
            ),
        )

    def test_a_dispute_is_an_error_and_an_email_to_support(
        self, api_client, user, variant, caplog, settings
    ):
        order = _order(user, variant, Order.Status.SHIPPED)

        with caplog.at_level("ERROR"):
            response = self._dispute(api_client)

        assert response.status_code == 200
        [alert] = mail.outbox
        assert alert.to == [settings.SUPPORT_EMAIL]
        assert f"order #{order.pk}" in alert.subject and "67.50 USD" in alert.subject
        assert "fraudulent" in alert.body and "2026-01-01" in alert.body
        assert any(r.levelname == "ERROR" and "DISPUTE" in r.getMessage() for r in caplog.records)
        assert _state(order, variant) == (Order.Status.SHIPPED, 7)

    def test_a_dispute_on_an_unknown_payment_still_alerts(self, api_client):
        response = self._dispute(api_client, intent_id="pi_unknown")

        assert response.status_code == 200
        assert len(mail.outbox) == 1
        assert "pi_unknown" in mail.outbox[0].subject
