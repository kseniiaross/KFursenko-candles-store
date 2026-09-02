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

from .emails import send_order_confirmation_email
from .models import Order

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
                order = (
                    Order.objects.select_for_update()
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
                metadata = {
                    "order_id": str(order.id),
                    "user_id": str(request.user.id),
                }

                intent = self._get_reusable_intent(order.stripe_payment_intent_id)

                # The shopper can go back and pick a different shipping rate
                # after the intent exists. Whatever the order says now is what
                # gets charged.
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
        order_to_email = None

        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .select_related("user")
                .prefetch_related("items")
                .filter(id=order_id, stripe_payment_intent_id=intent_id)
                .first()
            )

            if order and order.status != Order.Status.PAID:
                order.status = Order.Status.PAID
                order.save(update_fields=["status", "updated_at"])
                order_to_email = order

        # Outside the transaction: an SMTP timeout must not roll back a
        # payment we have already taken.
        if order_to_email:
            try:
                send_order_confirmation_email(order_to_email)
            except Exception:
                logger.exception(
                    "Order confirmation email failed for order_id=%s",
                    order_to_email.id,
                )

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
