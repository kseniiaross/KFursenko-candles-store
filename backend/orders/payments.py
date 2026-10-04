"""Stripe-side money handling for orders that won't ship.

Two jobs:

* Closing an order's PaymentIntent before the order itself is cancelled.
  Order matters: cancel the intent first, then the order. The other way
  round, a payment form still open in another tab could complete after the
  stock has gone back on the shelf.
* Refunding a payment that succeeded anyway on an order that is already
  CANCELED or REFUNDED — and making sure a person hears about it.
"""

import enum
import logging
from decimal import Decimal

import stripe
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


class IntentRelease(enum.Enum):
    # Nothing can be charged any more: the intent is cancelled now, was
    # already cancelled, or the order never had one.
    RELEASED = "released"
    # Stripe has taken the money or is in the middle of taking it. The
    # webhook will settle the order; it must not be cancelled.
    IN_PROGRESS = "in_progress"


def _intent_missing(error: stripe.InvalidRequestError, intent_id: str) -> bool:
    """Stripe has no such intent under this key, so nothing can charge it.

    Happens when the intent was created under the other mode's key (test vs
    live) or no longer exists. Stripe's message names the mode when that is
    the cause, so it goes in the log.
    """
    if getattr(error, "code", None) != "resource_missing":
        return False

    logger.warning(
        "PaymentIntent %s does not exist under the current Stripe key; "
        "treating it as released. Stripe said: %s",
        intent_id,
        getattr(error, "user_message", None) or str(error),
    )
    return True


def intent_exists(intent_id: str) -> bool:
    """Whether Stripe has this intent under the current key. Read-only.

    Raises stripe.StripeError when Stripe can't be asked (network, auth,
    5xx) — that is "unknown", not "missing".
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        stripe.PaymentIntent.retrieve(intent_id)
        return True
    except stripe.InvalidRequestError as error:
        if getattr(error, "code", None) == "resource_missing":
            return False
        raise


def release_payment_intent(intent_id: str) -> IntentRelease:
    """Cancel the PaymentIntent so it can no longer be paid.

    Raises stripe.StripeError when Stripe cannot be asked at all (network,
    auth, 5xx). Callers must treat that as "unknown" and leave the order
    alone. A 404 is not that: an intent Stripe doesn't have cannot be paid,
    which is exactly the guarantee cancelling the order needs.
    """
    if not intent_id:
        return IntentRelease.RELEASED

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        stripe.PaymentIntent.cancel(intent_id)
        return IntentRelease.RELEASED
    except stripe.InvalidRequestError as error:
        if _intent_missing(error, intent_id):
            return IntentRelease.RELEASED

        # Otherwise Stripe refused because the intent is already cancelled,
        # processing or succeeded. Only the first of those is safe.
        try:
            intent = stripe.PaymentIntent.retrieve(intent_id)
        except stripe.InvalidRequestError as retrieve_error:
            if _intent_missing(retrieve_error, intent_id):
                return IntentRelease.RELEASED
            raise

        if intent.status == "canceled":
            return IntentRelease.RELEASED

        logger.info(
            "PaymentIntent %s is %s; leaving its order for the webhook.",
            intent_id,
            intent.status,
        )
        return IntentRelease.IN_PROGRESS


def cancel_pending_order(order) -> IntentRelease:
    """Cancel an unpaid order and put its stock back.

    Returns IN_PROGRESS, without touching the order, when a payment is under
    way. Raises ValueError if the order is no longer PENDING (paid or
    cancelled in the meantime) and stripe.StripeError if Stripe can't be
    reached — in both cases nothing has changed.
    """
    from .models import Order

    outcome = release_payment_intent(order.stripe_payment_intent_id)

    if outcome is IntentRelease.IN_PROGRESS:
        return outcome

    order.transition_to(Order.Status.CANCELED)
    return outcome


# ======================================================
# PAYMENTS ON ORDERS THAT WON'T SHIP
# ======================================================
def refund_unfulfillable_payment(order, intent_id: str, intent_data: dict):
    """Refund a payment that succeeded on a CANCELED or REFUNDED order.

    Records a PaymentIncident and alerts staff. Safe to call again for the
    same intent (Stripe redelivers webhooks): it finds the existing incident,
    doesn't refund twice, and only alerts when the outcome changes.

    Returns the incident, or None when Stripe says the money was already
    refunded (a redelivery after a refund someone made by hand — nothing
    went wrong). Re-raises stripe.StripeError after recording a failed
    refund, so the webhook can answer 500 and Stripe retries later.
    """
    from .models import Order, PaymentIncident

    kind = (
        PaymentIncident.Kind.PAID_AFTER_REFUND
        if order.status == Order.Status.REFUNDED
        else PaymentIncident.Kind.PAID_AFTER_CANCEL
    )
    amount = (Decimal(int(intent_data.get("amount_received") or 0)) / 100).quantize(
        Decimal("0.01")
    )
    currency = (intent_data.get("currency") or order.currency or "usd").lower()

    incident = PaymentIncident.objects.filter(
        stripe_payment_intent_id=intent_id
    ).first()

    if incident and incident.outcome == PaymentIncident.Outcome.REFUNDED:
        return incident

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        refund = stripe.Refund.create(
            payment_intent=intent_id,
            # Shown on the refund in the Stripe dashboard.
            metadata={"order_id": str(order.pk), "reason": kind},
            idempotency_key=f"unfulfillable-{intent_id}",
        )
    except stripe.InvalidRequestError as error:
        if getattr(error, "code", None) == "charge_already_refunded":
            logger.info(
                "Payment %s on order %s was already refunded; nothing to do.",
                intent_id,
                order.pk,
            )
            if incident:
                incident.outcome = PaymentIncident.Outcome.REFUNDED
                incident.detail = "Already refunded at Stripe (by hand or an earlier attempt)."
                incident.save(update_fields=["outcome", "detail", "updated_at"])
            return incident
        _record_failure(order, intent_id, kind, amount, currency, incident, error)
        raise
    except stripe.StripeError as error:
        _record_failure(order, intent_id, kind, amount, currency, incident, error)
        raise

    if incident is None:
        incident = PaymentIncident(
            order=order,
            stripe_payment_intent_id=intent_id,
            kind=kind,
            amount=amount,
            currency=currency,
        )

    incident.outcome = PaymentIncident.Outcome.REFUNDED
    incident.stripe_refund_id = refund.id
    incident.detail = ""
    incident.save()

    _alert(incident)
    return incident


def _record_failure(order, intent_id, kind, amount, currency, incident, error):
    """Keep one row per payment; alert only the first time it fails, so a
    Stripe outage retried for three days doesn't send hundreds of emails."""
    from .models import PaymentIncident

    if incident is None:
        incident = PaymentIncident.objects.create(
            order=order,
            stripe_payment_intent_id=intent_id,
            kind=kind,
            outcome=PaymentIncident.Outcome.REFUND_FAILED,
            amount=amount,
            currency=currency,
            detail=str(error),
        )
        _alert(incident)
    else:
        incident.detail = str(error)
        incident.save(update_fields=["detail", "updated_at"])


def _alert(incident):
    """Tell a person, today. Logged at ERROR, and emailed to SUPPORT_EMAIL.

    The email is best-effort: with no SMTP credentials in production,
    settings.py falls back to the console backend and this lands in the log
    only. The PaymentIncident row in the admin is the record that can't be
    lost.
    """
    order = incident.order
    refunded = incident.outcome == incident.Outcome.REFUNDED

    subject = (
        f"[KFursenko] Refunded {incident.amount} {incident.currency.upper()} "
        f"paid on {order.get_status_display().lower()} order #{order.pk}"
        if refunded
        else f"[KFursenko] ACTION NEEDED: refund failed for order #{order.pk}"
    )
    body = "\n".join(
        [
            incident.get_kind_display() + ".",
            "",
            f"Order:           #{order.pk} ({order.get_status_display()})",
            f"Amount:          {incident.amount} {incident.currency.upper()}",
            f"PaymentIntent:   {incident.stripe_payment_intent_id}",
            f"Refund:          {incident.stripe_refund_id or '— none —'}",
            f"Outcome:         {incident.get_outcome_display()}",
            *([f"Stripe said:     {incident.detail}"] if incident.detail else []),
            "",
            "The order stays as it is and its stock has already been returned.",
            (
                "The customer has their money back; check the refund in the Stripe dashboard."
                if refunded
                else "Refund this payment by hand in the Stripe dashboard, then mark the incident resolved."
            ),
            f"Admin: /admin/orders/paymentincident/{incident.pk}/change/",
        ]
    )

    logger.error("%s\n%s", subject, body)

    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [settings.SUPPORT_EMAIL],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Could not email the payment incident alert for order %s", order.pk)
