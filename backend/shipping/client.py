"""Thin HTTP client for the Shippo API.

Deliberately not the official SDK: `requests` is already a dependency and the
surface we need is four endpoints. Keeping it here means retry policy, timeouts
and error mapping live in one readable place.

The token is never logged. Do not add the response body to a log line either —
Shippo echoes the address block back, which is customer PII.
"""

import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class ShippoError(Exception):
    """Any failure talking to Shippo: transport, HTTP or business-level."""

    def __init__(self, message, *, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class ShippoNotConfigured(ShippoError):
    """No token in the environment. Treated separately so callers can fall
    back to the flat rate instead of failing a checkout."""


class ShippoClient:
    def __init__(self, token=None, base_url=None, timeout=None):
        self.token = (token or settings.SHIPPO_TOKEN or "").strip()

        if not self.token:
            raise ShippoNotConfigured("SHIPPO_TOKEN is not set")

        self.base_url = (base_url or settings.SHIPPO_API_BASE).rstrip("/")
        self.timeout = timeout or settings.SHIPPO_TIMEOUT_SECONDS

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"ShippoToken {self.token}",
                "Content-Type": "application/json",
                "SHIPPO-API-VERSION": settings.SHIPPO_API_VERSION,
            }
        )

    @property
    def is_test(self) -> bool:
        return self.token.startswith("shippo_test_")

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------
    def _request(self, method, path, *, json=None, retries=0):
        """`retries` defaults to 0 on purpose.

        Retrying a POST that spends money is how you buy two labels for one
        order. Only read-only calls and rate quoting opt in.
        """
        url = f"{self.base_url}{path}"
        attempt = 0

        while True:
            attempt += 1

            try:
                response = self.session.request(
                    method, url, json=json, timeout=self.timeout
                )
            except requests.RequestException as exc:
                if attempt <= retries:
                    time.sleep(0.5 * attempt)
                    continue
                raise ShippoError(f"Shippo request failed: {exc.__class__.__name__}") from exc

            if response.status_code in RETRY_STATUSES and attempt <= retries:
                # Shippo sends Retry-After on 429; honour it when present.
                delay = response.headers.get("Retry-After")
                time.sleep(float(delay) if delay else 0.5 * attempt)
                continue

            break

        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {"detail": response.text[:500]}

            logger.warning(
                "Shippo %s %s -> %s", method, path, response.status_code
            )
            raise ShippoError(
                f"Shippo returned {response.status_code}",
                status_code=response.status_code,
                payload=body,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ShippoError("Shippo returned a non-JSON body") from exc

    # ------------------------------------------------------------------
    # endpoints
    # ------------------------------------------------------------------
    def create_shipment(self, payload):
        # Safe to retry: a duplicate shipment object costs nothing.
        return self._request("POST", "/shipments/", json=payload, retries=2)

    def get_rate(self, rate_id):
        return self._request("GET", f"/rates/{rate_id}", retries=2)

    def create_transaction(self, payload):
        # Never retried. See _request docstring.
        return self._request("POST", "/transactions/", json=payload, retries=0)

    def get_transaction(self, transaction_id):
        return self._request("GET", f"/transactions/{transaction_id}", retries=2)

    def create_refund(self, transaction_id):
        return self._request(
            "POST", "/refunds/", json={"transaction": transaction_id, "async": False}
        )
