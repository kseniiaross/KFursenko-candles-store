import json
import stripe

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction

from .models import Order


stripe.api_key = settings.STRIPE_SECRET_KEY


def create_payment_intent(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        order_id = data.get("order_id")

        if not order_id:
            return JsonResponse({"error": "Missing order_id"}, status=400)

        order = Order.objects.get(id=order_id)

        if order.status != Order.Status.PENDING:
            return JsonResponse({"error": "Order is not payable"}, status=400)

        amount = int(order.total_amount * 100)

        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            automatic_payment_methods={"enabled": True},
            metadata={
                "order_id": str(order.id),
            },
        )

        order.stripe_payment_intent_id = intent.id
        order.save(update_fields=["stripe_payment_intent_id"])

        return JsonResponse({
            "client_secret": intent.client_secret
        })

    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def stripe_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            endpoint_secret
        )
    except ValueError:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400)

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "payment_intent.succeeded":
        intent_id = data["id"]
        order_id = data["metadata"].get("order_id")

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                id=order_id,
                stripe_payment_intent_id=intent_id
            ).first()

            if order:
                order.status = Order.Status.PAID
                order.save(update_fields=["status", "updated_at"])

    if event_type == "payment_intent.payment_failed":
        intent_id = data["id"]
        order_id = data["metadata"].get("order_id")

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                id=order_id,
                stripe_payment_intent_id=intent_id
            ).first()

            if order:
                order.status = Order.Status.CANCELED
                order.save(update_fields=["status", "updated_at"])

    return HttpResponse(status=200)