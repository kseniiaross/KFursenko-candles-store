"""Every new account accepts the sign-up discount's terms, and the account
keeps a record of who accepted which words, and when."""

import hashlib
import re
from pathlib import Path

import pytest

from accounts.models import TermsAcceptance, User
from accounts.terms import TEMPLATES, current_terms
from candles.models import Offer

I18N = Path(__file__).resolve().parents[2] / "frontend/src/i18n.ts"
REGISTER_URL = "/api/accounts/register/"
TERMS_URL = "/api/accounts/terms/"

# The wording before ed56e22 ("Offer copy says what combines…"), as an old
# page would still have shown it.
OLD_WORDING = (
    "Create an account and 10% comes off your first order automatically at checkout — "
    "no code needed. Valid for 60 days after sign-up. Does not apply to candles already "
    "included in another promotion, or to shipping and tax."
)
OLD_VERSION = hashlib.sha256(OLD_WORDING.encode()).hexdigest()[:16]


@pytest.fixture
def welcome(db):
    return Offer.objects.create(
        title="New Shopper",
        kind=Offer.Kind.NEW_SHOPPER,
        discount_percent=10,
        new_shopper_days_active=60,
        apply_globally=True,
        show_badge=False,
    )


def _shopper(**extra):
    return {
        "email": "new@example.com",
        "password": "testpass123",
        "first_name": "Nina",
        "last_name": "New",
        "phone_number": "+1 555 0100",
        **extra,
    }


def test_the_wording_is_the_sign_up_modal_s_word_for_word():
    source = I18N.read_text()
    pairs = re.findall(
        r'\n        terms:\n\s*"([^"]*)",\n\s*termsNoLimit:\n\s*"([^"]*)"', source
    )

    assert [tuple(pair) for pair in pairs] == [TEMPLATES[locale] for locale in ("en", "ru", "es", "fr")]


@pytest.mark.django_db
class TestTermsEndpoint:
    def test_nothing_to_accept_when_no_sign_up_discount_runs(self, api_client):
        assert api_client.get(TERMS_URL).json() == {"terms": None}

    def test_the_running_offer_in_the_shopper_s_language(self, api_client, welcome):
        terms = api_client.get(TERMS_URL, {"locale": "ru"}).json()["terms"]

        assert terms["locale"] == "ru"
        assert terms["text"].startswith("Зарегистрируйтесь — и скидка 10% ")
        assert "Действует 60 дн. после регистрации." in terms["text"]
        assert "{{" not in terms["text"]

    def test_an_offer_without_a_time_limit_says_none(self, api_client, welcome):
        welcome.new_shopper_days_active = 0
        welcome.save()

        text = api_client.get(TERMS_URL).json()["terms"]["text"]

        assert text == TEMPLATES["en"][1].replace("{{percent}}", "10")

    def test_an_unknown_language_gets_english(self, api_client, welcome):
        assert api_client.get(TERMS_URL, {"locale": "de"}).json()["terms"]["locale"] == "en"


@pytest.mark.django_db
class TestRegisterRecordsAcceptance:
    def test_records_who_accepted_which_words_and_when(self, api_client, welcome):
        terms = current_terms("fr")

        response = api_client.post(
            REGISTER_URL, _shopper(terms_version=terms["version"], locale="fr"), format="json"
        )

        assert response.status_code == 201
        record = TermsAcceptance.objects.get()
        assert record.user.email == "new@example.com"
        assert record.version == terms["version"]
        assert record.locale == "fr"
        assert record.text == terms["text"]
        assert record.text.startswith("Créez un compte et 10% seront déduits")
        assert record.accepted_at is not None

    def test_no_acceptance_no_account(self, api_client, welcome):
        response = api_client.post(REGISTER_URL, _shopper(), format="json")

        assert response.status_code == 409
        assert response.json() == {"code": "terms_required", "terms": current_terms("en")}
        assert not User.objects.exists()

    def test_an_old_version_is_given_the_current_terms_and_can_then_sign_up(self, api_client, welcome):
        stale = api_client.post(
            REGISTER_URL, _shopper(terms_version=OLD_VERSION, locale="en"), format="json"
        )

        assert stale.status_code == 409
        body = stale.json()
        assert body["code"] == "terms_outdated"
        assert body["terms"]["text"].startswith("Create an account and 10% comes off")
        assert "except candles already on sale" in body["terms"]["text"]
        assert not User.objects.exists()

        # The page shows those terms, the shopper ticks again, and it goes through.
        retry = api_client.post(
            REGISTER_URL,
            _shopper(terms_version=body["terms"]["version"], locale="en"),
            format="json",
        )

        assert retry.status_code == 201
        assert TermsAcceptance.objects.get().text == body["terms"]["text"]

    def test_a_change_to_the_offer_is_a_new_version(self, api_client, welcome):
        shown = current_terms("en")
        welcome.discount_percent = 15
        welcome.save()

        response = api_client.post(
            REGISTER_URL, _shopper(terms_version=shown["version"]), format="json"
        )

        assert response.status_code == 409
        assert "15%" in response.json()["terms"]["text"]

    def test_the_form_s_own_errors_come_first(self, api_client, welcome):
        response = api_client.post(REGISTER_URL, _shopper(email="not-an-email"), format="json")

        assert response.status_code == 400
        assert "email" in response.json()

    def test_no_sign_up_discount_nothing_to_accept(self, api_client, db):
        response = api_client.post(REGISTER_URL, _shopper(), format="json")

        assert response.status_code == 201
        assert not TermsAcceptance.objects.exists()
