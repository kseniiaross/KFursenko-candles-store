import logging
from decimal import ROUND_HALF_UP, Decimal

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status, throttling
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .payments import refund_unfulfillable_payment

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeIntentUserThrottle(throttling.UserRateThrottle):
    scope = "stripe_intent_user"


class CreatePaymentIntentView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [StripeIntentUserThrottle]

    # PaymentIntent statuses that can still be confirmed/paid, so it's safe
    # to hand the same intent back to the client instead of creating a new
    # one. Anything else (succeeded, canceled, processing, ...) means a
    # fresh PaymentIntent is needed.
    REUSABLE_INTENT_STATUSES = frozenset(
        {"requires_payment_method", "requires_confirmation", "requires_action"}
    )

    def _get_reusable_intent(self, existing_intent_id):
        if not existing_intent_id:
            return None

        try:
            intent = stripe.PaymentIntent.retrieve(existing_intent_id)
        except stripe.StripeError:
            logger.warning(
                "Could not retrieve existing PaymentIntent %s; creating a new one.",
                existing_intent_id,
            )
            return None

        if intent.status not in self.REUSABLE_INTENT_STATUSES:
            return None

        return intent

    def _build_metadata(self, order, user):
        """What the Stripe dashboard will show alongside the charge.

        Stripe only ever sees one number — the total. Without this breakdown,
        answering "how much of this 32.50 was postage?" during a refund or a
        chargeback means opening the admin in another tab. Values are strings
        because Stripe stores metadata as strings regardless.

        Keep this small: Stripe allows 50 keys and 500 characters per value,
        and metadata is not the place for anything sensitive.
        """
        metadata = {
            "order_id": str(order.id),
            "user_id": str(user.id),
            "subtotal_amount": str(order.subtotal_amount),
            "shipping_amount": str(order.shipping_amount),
            "tax_amount": str(order.tax_amount),
        }

        if order.discount_amount > 0:
            metadata["discount_amount"] = str(order.discount_amount)
            # Truncated: offer titles are free text and Stripe caps values.
            metadata["discount_label"] = order.discount_label[:200]

        shipment = getattr(order, "shipment", None)

        if shipment and shipment.carrier:
            metadata["shipping_carrier"] = shipment.carrier
            metadata["shipping_service"] = shipment.service_level[:200]

        return metadata

    def _order_payload(self, order, intent):
        return {
            "client_secret": intent.client_secret,
            "total_amount": float(order.total_amount),
            "subtotal_amount": float(order.subtotal_amount),
            "shipping_amount": float(order.shipping_amount),
            "tax_amount": float(order.tax_amount),
            "discount_amount": float(order.discount_amount),
            "discount_label": order.discount_label,
        }

    def post(self, request):
        order_id = request.data.get("order_id")

        if not order_id:
            return Response(
                {"error": "Missing order_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                # Lock the order row only. The shipment may not exist, and
                # Postgres refuses FOR UPDATE on the nullable side of the
                # outer join select_related needs to read it.
                order = (
                    Order.objects.select_for_update(of=("self",))
                    .select_related("shipment")
                    .filter(id=order_id, user=request.user)
                    .first()
                )

                if not order:
                    return Response(
                        {"error": "Order not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if order.status != Order.Status.PENDING:
                    return Response(
                        {"error": "Order is not payable"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Stripe wants an integer number of cents. total_amount is
                # a Decimal, but int() truncates toward zero rather than
                # rounding - quantize to the nearest cent first so e.g.
                # 19.995 becomes 2000, not 1999.
                amount = int(
                    (order.total_amount * 100).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )

                if amount < 50:
                    return Response(
                        {"error": "Order amount is too low for Stripe"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                currency = order.currency or "usd"
                metadata = self._build_metadata(order, request.user)

                intent = self._get_reusable_intent(order.stripe_payment_intent_id)

                # The shopper can go back and pick a different shipping rate
                # after the intent exists. Whatever the order says now is what
                # gets charged — and the metadata has to follow, or the
                # dashboard would show the postage they first considered.
                if intent is not None and (
                    intent.amount != amount or intent.currency != currency
                ):
                    intent = stripe.PaymentIntent.modify(
                        intent.id,
                        amount=amount,
                        currency=currency,
                        metadata=metadata,
                    )

                if intent is None:
                    intent = stripe.PaymentIntent.create(
                        amount=amount,
                        currency=currency,
                        payment_method_types=["card"],
                        metadata=metadata,
                    )

                    order.stripe_payment_intent_id = intent.id
                    order.save(update_fields=["stripe_payment_intent_id"])

            return Response(self._order_payload(order, intent), status=status.HTTP_200_OK)

        except stripe.StripeError:
            # Never answer 200 here. The client reads this response to decide
            # whether to mount the payment form; a success shape on a failed
            # call shows the shopper a checkout that cannot complete.
            logger.exception("Stripe rejected the intent for order %s", order_id)

            return Response(
                {"error": "Payment could not be initialised. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except Exception:
            logger.exception("Payment intent failed for order %s", order_id)

            return Response(
                {"error": "Something went wrong preparing the payment."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


def _payment_succeeded(order_id, intent_id, intent_data):
    """Settle a successful payment according to where the order is now.

    Stripe delivers webhooks at least once and retries for days, so this
    sees the same event more than once and must only ever move an order
    forward:

    * PENDING  -> PAID. The normal case.
    * PAID, SHIPPED, COMPLETED -> nothing. A redelivery; writing PAID here
      used to roll shipped orders back.
    * CANCELED, REFUNDED -> the shopper paid for an order that will never
      ship and whose stock is already back on sale. Refund automatically and
      raise a PaymentIncident so a person sees it the same day.
    """
    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(id=order_id, stripe_payment_intent_id=intent_id)
            .first()
        )

        if order is None:
            logger.warning(
                "payment_intent.succeeded for order %s / intent %s matched no order.",
                order_id,
                intent_id,
            )
            return HttpResponse(status=200)

        if order.status == Order.Status.PENDING:
            order.transition_to(Order.Status.PAID)
            return HttpResponse(status=200)

        if order.status not in (Order.Status.CANCELED, Order.Status.REFUNDED):
            logger.info(
                "payment_intent.succeeded redelivered for order %s (%s); ignoring.",
                order.pk,
                order.status,
            )
            return HttpResponse(status=200)

    # Outside the lock: the refund is a network call, and the incident row
    # it writes is unique per intent, which is what makes a redelivery safe.
    try:
        refund_unfulfillable_payment(order, intent_id, intent_data)
    except stripe.StripeError:
        # Recorded and alerted already. 500 makes Stripe redeliver, which
        # retries the refund.
        return HttpResponse(status=500)

    return HttpResponse(status=200)


@csrf_exempt
def stripe_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    if not endpoint_secret:
        # Fail closed: without a real secret, stripe.Webhook.construct_event()
        # would verify the signature using an empty HMAC key, which anyone can
        # compute without knowing anything about this deployment - that is,
        # it would accept forged events from anyone, not just Stripe. Refuse
        # to process webhooks at all until a real secret is configured rather
        # than silently trusting unverified requests.
        logger.error(
            "STRIPE_WEBHOOK_SECRET is not configured; refusing to process "
            "the Stripe webhook request."
        )
        return HttpResponse(status=500)

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return HttpResponse(status=400)
    except stripe.SignatureVerificationError:
        return HttpResponse(status=400)

    event_type = event["type"]
    data = event["data"]["object"]
    intent_id = data.get("id")
    order_id = (data.get("metadata") or {}).get("order_id")

    if not order_id:
        # Not one of ours, or an event we never tagged. Acknowledge it so
        # Stripe stops retrying.
        logger.info("Webhook %s carried no order_id; ignoring.", event_type)
        return HttpResponse(status=200)

    if event_type == "payment_intent.succeeded":
        # No confirmation email is sent from here, on purpose. The shop sends
        # order confirmations by hand, and tracking emails come from Shippo.
        # The old automatic send rendered emails/orders/order_confirmation.txt
        # with a context that filled none of its variables, so every paying
        # customer got a blank order number, total and address. Do not
        # reinstate a send here without building the context that template
        # actually uses (see the note at the top of the template).
        return _payment_succeeded(order_id, intent_id, data)

    elif event_type == "payment_intent.payment_failed":
        # A declined card is not a cancelled order. Cancelling here is
        # terminal under ALLOWED_TRANSITIONS, so the shopper could never
        # retry with another card — the order would be dead and the stock
        # still held. Leave it PENDING and let them try again.
        logger.info(
            "Payment failed for order %s (intent %s); leaving it payable.",
            order_id,
            intent_id,
        )

    return HttpResponse(status=200)