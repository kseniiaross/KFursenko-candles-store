"""Turning our storage format into what Shippo accepts.

Two mismatches to bridge:

* `Order.shipping_country` holds a display name ("United States"), Shippo wants
  ISO-3166 alpha-2.
* `Order.shipping_state` is free text, but US domestic labels need the two
  letter USPS code.

Both were fine while shipping was a flat $15. They are not fine now.
"""

from decimal import Decimal

from django.conf import settings

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "washington dc": "DC", "washington d.c.": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "puerto rico": "PR", "guam": "GU", "virgin islands": "VI",
}

COUNTRIES = {
    "united states": "US", "united states of america": "US", "usa": "US",
    "canada": "CA", "mexico": "MX", "united kingdom": "GB", "uk": "GB",
    "great britain": "GB", "germany": "DE", "france": "FR", "spain": "ES",
    "italy": "IT", "netherlands": "NL", "belgium": "BE", "poland": "PL",
    "australia": "AU", "new zealand": "NZ", "japan": "JP",
}


class AddressError(ValueError):
    """Address cannot be expressed in a form Shippo will accept."""


def country_code(value: str) -> str:
    raw = (value or "").strip()

    if len(raw) == 2 and raw.isalpha():
        return raw.upper()

    code = COUNTRIES.get(raw.lower())

    if not code:
        raise AddressError(
            f"Unsupported country: {raw!r}. Add it to shipping.normalize.COUNTRIES."
        )

    return code


def state_code(value: str, country: str) -> str:
    raw = (value or "").strip()

    if country != "US":
        # Most non-US destinations take the province as free text, or omit it.
        return raw

    if len(raw) == 2 and raw.isalpha():
        return raw.upper()

    code = US_STATES.get(raw.lower())

    if not code:
        raise AddressError(f"Unrecognised US state: {raw!r}")

    return code


def order_to_address(order) -> dict:
    """Build the `address_to` block from a saved Order."""
    country = country_code(order.shipping_country)

    address = {
        "name": order.shipping_full_name.strip(),
        "street1": order.shipping_line1.strip(),
        "city": order.shipping_city.strip(),
        "state": state_code(order.shipping_state, country),
        "zip": order.shipping_postal_code.strip(),
        "country": country,
        "email": getattr(order.user, "email", "") or "",
    }

    if order.shipping_line2.strip():
        address["street2"] = order.shipping_line2.strip()

    phone = getattr(order, "shipping_phone", "") or settings.SHIPPO_FALLBACK_PHONE

    if phone:
        address["phone"] = phone

    return address


def payload_to_address(shipping: dict) -> dict:
    """Same thing, but from a validated ShippingSerializer dict.

    Used to quote rates at checkout, before any Order row exists.
    """
    country = country_code(shipping.get("country", "United States"))

    address = {
        "name": (shipping.get("full_name") or "").strip(),
        "street1": (shipping.get("line1") or "").strip(),
        "city": (shipping.get("city") or "").strip(),
        "state": state_code(shipping.get("state", ""), country),
        "zip": (shipping.get("postal_code") or "").strip(),
        "country": country,
    }

    if (shipping.get("line2") or "").strip():
        address["street2"] = shipping["line2"].strip()

    if settings.SHIPPO_FALLBACK_PHONE:
        address["phone"] = settings.SHIPPO_FALLBACK_PHONE

    return address


# ----------------------------------------------------------------------
# Parcels
# ----------------------------------------------------------------------
def build_parcels(lines) -> list[dict]:
    """`lines` is an iterable of (variant, quantity).

    Naive cartonisation: sum the volume, pick the smallest box that holds it,
    spill into more boxes of the largest size if it does not fit. Good enough
    for candles, which are dense and similar in shape. If you ever ship a
    12-pack gift set, revisit this — real bin packing it is not.
    """
    total_weight = Decimal("0")
    total_volume = Decimal("0")
    longest_side = Decimal("0")

    for variant, qty in lines:
        qty = Decimal(qty)

        weight = variant.weight_oz or Decimal("0")
        length = variant.length_in or Decimal("0")
        width = variant.width_in or Decimal("0")
        height = variant.height_in or Decimal("0")

        if weight <= 0:
            raise AddressError(
                f"Variant #{variant.id} has no shipping weight set."
            )

        total_weight += weight * qty
        total_volume += length * width * height * qty
        longest_side = max(longest_side, length, width, height)

    boxes = sorted(settings.SHIPPO_BOXES, key=lambda b: b["length"] * b["width"] * b["height"])

    for box in boxes:
        capacity = Decimal(box["length"]) * Decimal(box["width"]) * Decimal(box["height"])
        fits_dimension = longest_side <= max(box["length"], box["width"], box["height"])

        # 0.80 leaves room for wrap and void fill; candles do not tessellate.
        if fits_dimension and total_volume <= capacity * Decimal("0.80"):
            return [_parcel(box, total_weight + Decimal(str(box["tare_oz"])))]

    # Overflow: split across N copies of the biggest box, weight spread evenly.
    box = boxes[-1]
    capacity = Decimal(box["length"]) * Decimal(box["width"]) * Decimal(box["height"])
    count = max(1, int((total_volume / (capacity * Decimal("0.80"))).to_integral_value(rounding="ROUND_CEILING")))

    per_box = (total_weight / count) + Decimal(str(box["tare_oz"]))

    return [_parcel(box, per_box) for _ in range(count)]


def _parcel(box, weight_oz: Decimal) -> dict:
    return {
        "length": str(box["length"]),
        "width": str(box["width"]),
        "height": str(box["height"]),
        "distance_unit": "in",
        "weight": str(weight_oz.quantize(Decimal("0.01"))),
        "mass_unit": "oz",
    }
