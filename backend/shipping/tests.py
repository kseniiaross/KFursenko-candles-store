"""No test hits the network. Shippo's test mode is still a remote service with
rate limits, and a suite that needs Wi-Fi is a suite people stop running."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.test import override_settings

from shipping.client import ShippoError
from shipping.models import Shipment
from shipping.normalize import (AddressError, build_parcels, country_code,
                                state_code)
from shipping.services import purchase_label, quote_rates

pytestmark = pytest.mark.django_db


# ----------------------------------------------------------------------
# normalize
# ----------------------------------------------------------------------
def test_country_display_name_becomes_iso_code():
    assert country_code("United States") == "US"
    assert country_code("us") == "US"


def test_unknown_country_is_rejected_loudly():
    with pytest.raises(AddressError):
        country_code("Atlantis")


def test_state_name_becomes_usps_code():
    assert state_code("California", "US") == "CA"
    assert state_code("ca", "US") == "CA"


def test_non_us_state_passes_through_untouched():
    assert state_code("Ontario", "CA") == "Ontario"


def test_parcel_weight_includes_box_tare():
    variant = MagicMock(
        id=1,
        weight_oz=Decimal("8"),
        length_in=Decimal("3"),
        width_in=Decimal("3"),
        height_in=Decimal("4"),
    )

    parcels = build_parcels([(variant, 2)])

    assert len(parcels) == 1
    # 2 x 8oz of candle plus whatever the chosen box weighs.
    assert Decimal(parcels[0]["weight"]) > Decimal("16")
    assert parcels[0]["mass_unit"] == "oz"


def test_variant_without_weight_is_a_hard_error():
    variant = MagicMock(id=7, weight_oz=Decimal("0"))

    with pytest.raises(AddressError):
        build_parcels([(variant, 1)])


# ----------------------------------------------------------------------
# services
# ----------------------------------------------------------------------
def _variant():
    return MagicMock(
        id=1,
        weight_oz=Decimal("8"),
        length_in=Decimal("3"),
        width_in=Decimal("3"),
        height_in=Decimal("4"),
    )


def test_quote_rates_returns_cheapest_first():
    client = MagicMock()
    client.create_shipment.return_value = {
        "object_id": "ship_1",
        "status": "SUCCESS",
        "address_to": {"validation_results": {"is_valid": True}},
        "rates": [
            {
                "object_id": "rate_fast",
                "amount": "24.50",
                "currency": "USD",
                "provider": "USPS",
                "servicelevel": {"name": "Priority Express"},
            },
            {
                "object_id": "rate_slow",
                "amount": "8.15",
                "currency": "USD",
                "provider": "USPS",
                "servicelevel": {"name": "Ground Advantage"},
            },
        ],
    }

    rates = quote_rates(address_to={}, lines=[(_variant(), 1)], client=client)

    assert [r["rate_id"] for r in rates] == ["rate_slow", "rate_fast"]
    assert rates[0]["amount"] == Decimal("8.15")


def test_empty_rate_list_names_the_usual_cause():
    client = MagicMock()
    client.create_shipment.return_value = {
        "object_id": "ship_1",
        "status": "SUCCESS",
        "address_to": {"validation_results": {"is_valid": True}},
        "rates": [],
    }

    with pytest.raises(ShippoError, match="carrier"):
        quote_rates(address_to={}, lines=[(_variant(), 1)], client=client)


def test_undeliverable_address_surfaces_the_carrier_message():
    client = MagicMock()
    client.create_shipment.return_value = {
        "object_id": "ship_1",
        "status": "SUCCESS",
        "address_to": {
            "validation_results": {
                "is_valid": False,
                "messages": [{"text": "Street number is missing"}],
            }
        },
        "rates": [],
    }

    with pytest.raises(AddressError, match="Street number"):
        quote_rates(address_to={}, lines=[(_variant(), 1)], client=client)


def test_second_purchase_does_not_buy_a_second_label(paid_order):
    client = MagicMock()
    client.is_test = True
    client.create_transaction.return_value = {
        "object_id": "txn_1",
        "status": "SUCCESS",
        "tracking_number": "9400100000000000000000",
        "label_url": "https://example.test/label.pdf",
    }

    Shipment.objects.create(order=paid_order, rate_id="rate_1")

    first = purchase_label(paid_order, client=client)
    second = purchase_label(paid_order, client=client)

    assert first.pk == second.pk
    assert client.create_transaction.call_count == 1


def test_failed_purchase_leaves_a_readable_reason(paid_order):
    client = MagicMock()
    client.is_test = True
    client.create_transaction.return_value = {
        "object_id": "txn_2",
        "status": "ERROR",
        "messages": [{"text": "Insufficient funds"}],
    }

    Shipment.objects.create(order=paid_order, rate_id="rate_1")

    with pytest.raises(ShippoError):
        purchase_label(paid_order, client=client)

    shipment = Shipment.objects.get(order=paid_order)

    assert shipment.status == Shipment.Status.FAILED
    assert "Insufficient funds" in shipment.error_message
