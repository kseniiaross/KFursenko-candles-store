"""Limits on what Lumière costs and what it will talk about.

The throttle counters live in the database, so every gunicorn worker counts
against the same quota; each Lumière endpoint also has a daily cap per IP;
replies have a token ceiling; and the prompt keeps Lumière to the shop.
"""

from unittest.mock import patch

import pytest
from django.db import connection
from django.test import override_settings

from lumiere import services, views

REPLY_URL = "/api/lumiere/reply/"
SEARCH_URL = "/api/lumiere/search/"

DATABASE_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}


def _reply(client, ip="203.0.113.1"):
    return client.post(
        REPLY_URL, {"text": "Something fresh?"}, format="json", REMOTE_ADDR=ip
    )


def _search(client, ip="203.0.113.1"):
    return client.post(
        SEARCH_URL, {"query": "fresh"}, format="json", REMOTE_ADDR=ip
    )


class TestSharedThrottleCounters:
    def test_production_uses_the_database_cache(self):
        # The suite runs on the in-memory cache (conftest clears it before
        # every test, without database access); production must not.
        from config import settings as production

        assert production.CACHES == DATABASE_CACHE

    @pytest.mark.django_db
    def test_the_migration_creates_the_cache_table(self):
        assert "django_cache" in connection.introspection.table_names()

    @pytest.mark.django_db
    def test_throttle_counts_are_stored_in_the_shared_table(self, api_client):
        with override_settings(CACHES=DATABASE_CACHE):
            from django.core.cache import caches

            caches["default"].clear()
            for _ in range(20):
                assert _reply(api_client).status_code == 200

            # Kept in the table every worker reads, not in one process.
            with connection.cursor() as cursor:
                cursor.execute("SELECT cache_key FROM django_cache")
                keys = [row[0] for row in cursor.fetchall()]

            assert any("lumiere_anon" in key for key in keys)
            assert _reply(api_client).status_code == 429


@pytest.mark.django_db
class TestDailyCap:
    def test_configured_at_one_hundred_a_day(self, settings):
        from rest_framework.settings import api_settings

        assert api_settings.DEFAULT_THROTTLE_RATES["lumiere_daily"] == "100/day"
        assert views.LumiereDailyThrottle in views.LumiereReplyView.throttle_classes
        assert views.LumiereDailyThrottle in views.LumiereSearchView.throttle_classes

    def test_both_endpoints_draw_on_one_daily_quota_per_ip(self, api_client):
        # A class-level rate takes precedence over the settings one.
        with patch.object(views.LumiereDailyThrottle, "rate", "3/day", create=True):
            assert _reply(api_client).status_code == 200
            assert _search(api_client).status_code == 200
            assert _reply(api_client).status_code == 200

            # Under the per-minute limits, but over the day's.
            assert _reply(api_client).status_code == 429
            assert _search(api_client).status_code == 429

            # Another address has its own day.
            assert _reply(api_client, ip="203.0.113.2").status_code == 200


class TestReplyLength:
    def test_reply_request_caps_output_tokens(self, settings):
        settings.OPENAI_API_KEY = "test-key"

        with patch.object(services, "_call_openai_payload") as call:
            call.return_value = {"output_text": "Try Matcha Chill."}
            services.call_openai_reply(
                locale="en", user_name=None, user_text="hi", store_context=""
            )

        payload = call.call_args.args[0]
        assert payload["max_output_tokens"] == settings.OPENAI_MAX_OUTPUT_TOKENS
        assert 0 < payload["max_output_tokens"] <= 500


class TestStaysOnTopic:
    def test_instructions_decline_other_subjects(self):
        instructions = services._build_instructions("en", None)

        assert "candles, this shop, shipping, or orders" in instructions
        assert "decline in one short sentence" in instructions


def _throttles_in_use():
    """Every throttle class an endpoint can apply."""
    from rest_framework.settings import api_settings

    from orders.views import OrderCreateThrottle
    from orders.views_stripe import StripeIntentUserThrottle
    from shipping.views import ShippingRatesThrottle

    return [
        *api_settings.DEFAULT_THROTTLE_CLASSES,
        views.LumiereAnonThrottle,
        views.LumiereUserThrottle,
        views.LumiereSearchThrottle,
        views.LumiereDailyThrottle,
        OrderCreateThrottle,
        StripeIntentUserThrottle,
        ShippingRatesThrottle,
    ]


def _drf_request(**meta):
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    return Request(APIRequestFactory().post("/", **meta))


class TestClientIdentity:
    """Railway's edge sets X-Real-IP to the caller's address. X-Forwarded-For
    is undocumented there, and DRF used all of it as the identity."""

    @pytest.mark.parametrize("throttle", _throttles_in_use(), ids=lambda c: c.__name__)
    def test_x_real_ip_is_the_identity(self, throttle):
        request = _drf_request(
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_REAL_IP="198.51.100.7",
            HTTP_X_FORWARDED_FOR="203.0.113.99",
        )

        assert throttle().get_ident(request) == "198.51.100.7"

    def test_without_the_header_drf_decides_as_before(self):
        from config.throttling import RealIPAnonRateThrottle

        request = _drf_request(REMOTE_ADDR="127.0.0.1")

        assert RealIPAnonRateThrottle().get_ident(request) == "127.0.0.1"

    @pytest.mark.parametrize("value", ["", "  ", "not-an-ip", "1.2.3.4, 5.6.7.8"])
    def test_a_malformed_header_is_ignored(self, value):
        from config.throttling import RealIPAnonRateThrottle

        request = _drf_request(REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP=value)

        assert RealIPAnonRateThrottle().get_ident(request) == "127.0.0.1"

    @pytest.mark.django_db
    def test_a_new_forwarded_for_value_does_not_buy_more_requests(self, api_client):
        def reply(forwarded_for, real_ip="198.51.100.7"):
            return api_client.post(
                REPLY_URL,
                {"text": "Something fresh?"},
                format="json",
                REMOTE_ADDR="10.0.0.1",
                HTTP_X_REAL_IP=real_ip,
                HTTP_X_FORWARDED_FOR=forwarded_for,
            )

        for n in range(20):
            assert reply(f"203.0.113.{n}").status_code == 200

        assert reply("203.0.113.250").status_code == 429
        assert reply("203.0.113.250", real_ip="198.51.100.8").status_code == 200


def _openai(text, *, cut=False):
    data = {"status": "completed", "output_text": text}
    if cut:
        data = {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output_text": text,
        }
    return data


class TestReplyCutAtTheCap:
    def _reply(self, settings, data, locale="en"):
        settings.OPENAI_API_KEY = "test-key"
        with patch.object(services, "_call_openai_payload", return_value=data):
            return services.call_openai_reply(
                locale=locale, user_name=None, user_text="hi", store_context=""
            )

    def test_the_unfinished_sentence_is_dropped(self, settings):
        text = self._reply(
            settings,
            _openai("Matcha Chill suits a bedroom. It is $18.49 in 8 oz. The tea notes are soft and cit", cut=True),
        )

        assert text == "Matcha Chill suits a bedroom. It is $18.49 in 8 oz."

    def test_with_no_whole_sentence_the_shopper_gets_a_short_apology(self, settings):
        text = self._reply(
            settings, _openai("Matcha Chill suits a bedroom with green tea and", cut=True)
        )

        assert "green tea and" not in text
        assert text == services._t(
            "en", *services.CUT_REPLY_FALLBACK
        )

    def test_a_finished_reply_is_left_alone(self, settings):
        assert self._reply(settings, _openai("Try Matcha Chill")) == "Try Matcha Chill"


@pytest.mark.django_db
class TestSearchCap:
    def test_search_request_caps_output_tokens(self, settings, variant):
        settings.OPENAI_API_KEY = "test-key"

        with patch.object(services, "_call_openai_payload") as call:
            call.return_value = _openai('{"text": "Fresh.", "product_ids": [], "reasons": {}}')
            services.ai_search_candles("fresh")

        payload = call.call_args.args[0]
        assert payload["max_output_tokens"] == settings.OPENAI_SEARCH_MAX_OUTPUT_TOKENS
        assert 0 < payload["max_output_tokens"] <= 1000

    def test_a_cut_off_answer_falls_back_and_is_not_cached(self, settings, variant):
        from django.core.cache import cache

        settings.OPENAI_API_KEY = "test-key"
        cut = _openai(f'{{"text": "Fresh picks.", "product_ids": [{variant.candle_id}', cut=True)

        with patch.object(services, "_call_openai_payload", return_value=cut):
            result = services.ai_search_candles("fresh")

        assert "temporarily using catalog matching" in result["text"]
        assert cache.get(services._cache_key("ai_search_picks", "fresh", "en", 6)) is None
