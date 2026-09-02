"""Everything that talks to Shippo, wrapped so views stay dumb."""

import logging
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from .client import ShippoClient, ShippoError, ShippoNotConfigured
from .models import Shipment
from .normalize import AddressError, build_parcels, order_to_address

logger = logging.getLogger(__name__)


def _limit_per_carrier(rates, limit):
    """Keep the `limit` cheapest options per carrier.

    `rates` arrives sorted by price, so taking the first N per provider gives
    the cheap one and one step up — which is the choice customers actually
    make. Fifteen near-identical USPS tiers is not a choice, it is a wall.
    """
    if not limit:
        return rates

    seen = defaultdict(int)
    kept = []

    for rate in rates:
        carrier = rate["carrier"].lower()

        if seen[carrier] >= limit:
            continue

        seen[carrier] += 1
        kept.append(rate)

    return kept


def quote_rates(*, address_to: dict, lines, client=None) -> list[dict]:
    """Ask Shippo what this parcel costs to each service.

    `lines` is an iterable of (variant, quantity). Result is sorted cheapest
    first across all carriers, then trimmed per carrier — that order matters,
    since trimming first would keep two arbitrary rates instead of two cheap
    ones.
    """
    client = client or ShippoClient()
    parcels = build_parcels(lines)

    data = client.create_shipment(
        {
            "address_from": settings.SHIPPO_ADDRESS_FROM,
            "address_to": address_to,
            "parcels": parcels,
            "async": False,
        }
    )

    if data.get("status") == "ERROR":
        raise ShippoError("Shipment could not be created", payload=data)

    validation = (data.get("address_to") or {}).get("validation_results") or {}

    if validation.get("is_valid") is False:
        messages = [m.get("text", "") for m in validation.get("messages", [])]
        raise AddressError(
            "; ".join(m for m in messages if m) or "Address is not deliverable"
        )

    rates = data.get("rates") or []

    if not rates:
        # Almost always an inactive carrier rather than a code bug.
        raise ShippoError(
            "Shippo returned no rates. Check that a carrier is enabled in "
            "Settings -> Carriers for this token's mode."
        )

    rates.sort(key=lambda r: Decimal(r["amount"]))

    normalized = [
        {
            "rate_id": rate["object_id"],
            "carrier": rate.get("provider", ""),
            "service_level": (rate.get("servicelevel") or {}).get("name", ""),
            "amount": Decimal(rate["amount"]),
            "currency": rate.get("currency", "USD"),
            "estimated_days": rate.get("estimated_days"),
            "duration_terms": rate.get("duration_terms", ""),
            "shipment_id": data["object_id"],
        }
        for rate in rates
    ]

    allowed = {c.lower() for c in getattr(settings, "SHIPPO_CARRIERS", [])}

    if allowed:
        normalized = [r for r in normalized if r["carrier"].lower() in allowed]

    # getattr keeps this working if the setting was never added.
    limit = getattr(settings, "SHIPPO_MAX_RATES_PER_CARRIER", 2)

    return _limit_per_carrier(normalized, limit)


def verify_rate(rate_id: str, client=None) -> dict:
    """Re-read a rate from Shippo before trusting its price.

    The storefront sends back a rate_id it got from us. Nothing stops a client
    from sending a different, cheaper one — the id alone is not proof of price.
    Always charge the amount Shippo reports here, never the amount the client
    claims.
    """
    client = client or ShippoClient()
    rate = client.get_rate(rate_id)

    return {
        "rate_id": rate["object_id"],
        "carrier": rate.get("provider", ""),
        "service_level": (rate.get("servicelevel") or {}).get("name", ""),
        "amount": Decimal(rate["amount"]),
        "currency": rate.get("currency", "USD"),
    }


def resolve_shipping_cost(*, address_to, lines, rate_id=None):
    """Price used by build_order. Never raises for infrastructure reasons.

    A shipping API being down must not stop a customer paying us. Falls back to
    the historical flat rate and returns None for the rate, so nothing
    downstream believes it has a real quote.
    """
    try:
        if rate_id:
            rate = verify_rate(rate_id)
            return rate["amount"], rate

        rates = quote_rates(address_to=address_to, lines=lines)
        return rates[0]["amount"], rates[0]

    except (ShippoError, ShippoNotConfigured) as exc:
        logger.warning("Shippo quote failed, using flat rate: %s", exc)
        return settings.SHIPPING_FALLBACK_RATE, None


def purchase_label(order, *, client=None) -> Shipment:
    """Buy the label for an order. Idempotent by status guard.

    The network call sits outside the transaction on purpose: holding a row
    lock for the 2-5 seconds Shippo takes to answer would serialise the whole
    admin under load.
    """
    with transaction.atomic():
        shipment, _ = Shipment.objects.select_for_update().get_or_create(order=order)

        if shipment.status == Shipment.Status.PURCHASED:
            return shipment

        if shipment.status == Shipment.Status.PURCHASING:
            raise ShippoError("A label purchase for this order is already running.")

        shipment.status = Shipment.Status.PURCHASING
        shipment.error_message = ""
        shipment.save(update_fields=["status", "error_message", "updated_at"])

    client = client or ShippoClient()

    try:
        rate_id = shipment.rate_id

        if not rate_id:
            # No quote survived checkout (flat-rate fallback, or an expired
            # rate). Re-quote now and take the cheapest.
            lines = []

            for item in order.items.select_related("variant", "candle").all():
                variant = item.variant or item.candle.variants.first()

                if variant is None:
                    raise ShippoError(
                        f"Order item {item.id} has no variant to weigh."
                    )

                lines.append((variant, item.quantity))

            rates = quote_rates(
                address_to=order_to_address(order), lines=lines, client=client
            )
            rate_id = rates[0]["rate_id"]

        data = client.create_transaction(
            {
                "rate": rate_id,
                "label_file_type": settings.SHIPPO_LABEL_FILE_TYPE,
                "async": False,
                "metadata": f"order:{order.id}",
            }
        )

        if data.get("status") != "SUCCESS":
            messages = [m.get("text", "") for m in data.get("messages", [])]
            raise ShippoError(
                "; ".join(m for m in messages if m) or "Label purchase failed"
            )

    except Exception as exc:
        Shipment.objects.filter(pk=shipment.pk).update(
            status=Shipment.Status.FAILED,
            error_message=str(exc)[:2000],
        )
        raise

    shipment.status = Shipment.Status.PURCHASED
    shipment.rate_id = rate_id
    shipment.transaction_id = data["object_id"]
    shipment.tracking_number = data.get("tracking_number", "") or ""
    shipment.tracking_url = data.get("tracking_url_provider", "") or ""
    shipment.label_url = data.get("label_url", "") or ""
    shipment.is_test = client.is_test
    shipment.error_message = ""
    shipment.save()

    logger.info("Bought label for order %s (test=%s)", order.id, client.is_test)

    return shipment


def refund_label(shipment: Shipment, *, client=None) -> Shipment:
    """Void an unused label. Money comes back on the carrier's schedule,
    not immediately."""
    if shipment.status != Shipment.Status.PURCHASED:
        raise ShippoError("Only a purchased label can be refunded.")

    client = client or ShippoClient()
    client.create_refund(shipment.transaction_id)

    shipment.status = Shipment.Status.REFUNDED
    shipment.save(update_fields=["status", "updated_at"])

    return shipment