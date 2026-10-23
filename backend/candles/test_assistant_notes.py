"""Lumière's notes are edited in the admin and never served to shoppers.

Candle.assistant_notes and burn_time go into the assistant's prompt only;
the catalogue API must not return them (CandleSerializer would, through
fields="__all__", if they weren't excluded by name).
"""

import pytest

from candles.models import Candle

LIST_URL = "/api/candles/candles/"

NOTES = "Green tea and steamed milk; suits a calm desk. Pairs with Mango Island."


@pytest.fixture
def noted(db, category):
    return Candle.objects.create(
        category=category,
        name="Matcha Chill",
        size="8 oz",
        assistant_notes=NOTES,
        burn_time="45–50 hours",
    )


def _rows(response):
    data = response.json()
    return data["results"] if isinstance(data, dict) else data


@pytest.mark.django_db
class TestNotServedToShoppers:
    def test_not_in_the_catalogue_list(self, api_client, noted):
        response = api_client.get(LIST_URL)

        assert response.status_code == 200
        [row] = [row for row in _rows(response) if row["id"] == noted.id]
        assert "assistant_notes" not in row
        assert "burn_time" not in row
        assert NOTES not in response.content.decode()

    def test_not_on_the_product_page(self, api_client, noted):
        response = api_client.get(f"{LIST_URL}{noted.slug}/")

        assert response.status_code == 200
        assert "assistant_notes" not in response.json()
        assert "burn_time" not in response.json()
        assert NOTES not in response.content.decode()

    def test_staff_get_them_through_the_admin_not_the_api(self, staff_client, noted):
        response = staff_client.get(f"{LIST_URL}{noted.slug}/")

        assert response.status_code == 200
        assert "assistant_notes" not in response.json()


@pytest.fixture
def boss(client):
    from accounts.models import User

    user = User.objects.create_superuser(email="boss@example.com", password="pw-12345!")
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestAdmin:
    def test_the_candle_page_has_the_lumiere_section(self, boss, noted):
        page = boss.get(f"/admin/candles/candle/{noted.pk}/change/").content.decode()

        assert "Lumière only" in page
        assert 'name="assistant_notes"' in page
        assert 'name="burn_time"' in page
        assert NOTES in page

    def test_missing_filter_counts_a_scent_covered_by_another_size(
        self, boss, noted, category
    ):
        bigger = Candle.objects.create(category=category, name="Matcha Chill", size="11.3 oz")
        bare = Candle.objects.create(category=category, name="Woman Body", size="8 oz")

        missing = boss.get("/admin/candles/candle/?lumiere_notes=missing")
        written = boss.get("/admin/candles/candle/?lumiere_notes=written")

        assert [c.pk for c in missing.context["cl"].result_list] == [bare.pk]
        assert {c.pk for c in written.context["cl"].result_list} == {noted.pk, bigger.pk}
