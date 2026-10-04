"""Closing an order's PaymentIntent before the order itself is cancelled.

Order matters: cancel the intent first, then the order. The other way round,
a payment form still open in another tab could complete after the stock has
gone back on the shelf, and the webhook would mark a cancelled order paid.
"""

import enum
import logging

import stripe
from django.conf import settings

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
