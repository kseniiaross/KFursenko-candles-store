"""The sign-up modal reads the welcome offer from here, so what it promises
is what checkout gives — and it doesn't appear when there's nothing to give.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from candles.models import Offer

URL = "/api/orders/welcome-offer/"


def _welcome(**fields):
    defaults = dict(
        title="Welcome 15%",
        kind=Offer.Kind.NEW_SHOPPER,
        discount_percent=15,
        new_shopper_days_active=45,
        apply_globally=True,
        show_badge=False,
        priority=30,
    )
    return Offer.objects.create(**{**defaults, **fields})


@pytest.mark.django_db
class TestWelcomeOfferEndpoint:
    def test_a_guest_sees_the_percent_and_how_long_it_lasts(self, api_client):
        _welcome()

        response = api_client.get(URL)

        assert response.status_code == 200
        assert response.json() == {
            "welcome_offer": {
                "title": "Welcome 15%",
                "discount_percent": 15,
                "days_after_signup": 45,
            }
        }

    def test_no_time_limit_is_null_not_zero(self, api_client):
        _welcome(new_shopper_days_active=0)

        response = api_client.get(URL)

        assert response.json()["welcome_offer"]["days_after_signup"] is None

    def test_none_running_is_null(self, api_client):
        # Other offers don't count: only the sign-up discount.
        Offer.objects.create(title="Spooky Season", kind=Offer.Kind.HOLIDAY, discount_percent=5)

        response = api_client.get(URL)

        assert response.status_code == 200
        assert response.json() == {"welcome_offer": None}

    @pytest.mark.parametrize(
        "fields",
        [
            {"is_active": False},
            {"discount_percent": None},
            {"offer_end": timezone.now() - timedelta(days=1)},
            {"offer_start": timezone.now() + timedelta(days=1)},
        ],
        ids=["switched-off", "no-percent", "ended", "not-started"],
    )
    def test_an_offer_checkout_wouldnt_apply_is_not_advertised(self, api_client, fields):
        _welcome(**fields)

        response = api_client.get(URL)

        assert response.json() == {"welcome_offer": None}

    def test_the_same_offer_checkout_would_pick(self, api_client):
        # Lowest priority number wins, as in get_welcome_offer.
        _welcome(title="Welcome 10%", discount_percent=10, priority=50)
        _welcome(title="Welcome 20%", discount_percent=20, priority=20)

        response = api_client.get(URL)

        assert response.json()["welcome_offer"]["discount_percent"] == 20
