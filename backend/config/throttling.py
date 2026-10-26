"""Throttles that identify an anonymous client by X-Real-IP.

DRF's default identity is the whole X-Forwarded-For header (NUM_PROXIES is
unset, because Railway doesn't publish a fixed hop count). Railway's
documented header for the client's address is X-Real-IP, set by its edge on
public traffic, so a client can't choose its own identity by sending a new
X-Forwarded-For.

Without the header (local runs, tests) or with a value that isn't an IP
address, DRF's own get_ident decides, as before. Requests over Railway's
private network skip the edge, so another service in the project could set
X-Real-IP itself; no other service calls this API.
"""

import ipaddress

from rest_framework import throttling


class RealIPMixin:
    def get_ident(self, request):
        real_ip = request.META.get("HTTP_X_REAL_IP", "").strip()

        try:
            return str(ipaddress.ip_address(real_ip))
        except ValueError:
            return super().get_ident(request)


class RealIPAnonRateThrottle(RealIPMixin, throttling.AnonRateThrottle):
    pass


class RealIPUserRateThrottle(RealIPMixin, throttling.UserRateThrottle):
    """Signed-in users are still counted by account; the address is only
    the identity for anonymous requests."""
