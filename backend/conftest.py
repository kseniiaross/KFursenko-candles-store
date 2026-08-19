import pytest
from rest_framework.test import APIClient

from accounts.models import User
from candles.models import Candle, CandleVariant, Category


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="shopper@example.com", password="testpass123")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="other@example.com", password="testpass123")


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        email="staff@example.com", password="testpass123", is_staff=True
    )


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def other_auth_client(api_client, other_user):
    api_client.force_authenticate(user=other_user)
    return api_client


@pytest.fixture
def staff_client(api_client, staff_user):
    api_client.force_authenticate(user=staff_user)
    return api_client


@pytest.fixture
def category(db):
    return Category.objects.create(name="Signature")


@pytest.fixture
def candle(db, category):
    return Candle.objects.create(
        category=category,
        name="Vanilla Dream",
        price="24.00",
        stock_qty=10,
    )


@pytest.fixture
def variant(db, candle):
    return CandleVariant.objects.create(
        candle=candle,
        size="Medium",
        price="24.00",
        stock_qty=10,
        is_active=True,
    )


@pytest.fixture
def out_of_stock_variant(db, candle):
    return CandleVariant.objects.create(
        candle=candle,
        size="Small",
        price="18.00",
        stock_qty=0,
        is_active=True,
    )


@pytest.fixture
def inactive_variant(db, candle):
    return CandleVariant.objects.create(
        candle=candle,
        size="Large",
        price="32.00",
        stock_qty=5,
        is_active=False,
    )
