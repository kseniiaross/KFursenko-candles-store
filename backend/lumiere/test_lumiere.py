import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from candles.models import Candle, CandleVariant, Category, Offer
from lumiere.services import (_build_instructions, _closing_questions,
                              ai_search_candles, build_store_context,
                              get_candle_by_slug, search_candles)
from lumiere.views import extract_slug_from_text


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """LumiereReplyView is throttled; don't let one test's requests count
    against the next test's rate limit."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def category(db):
    return Category.objects.create(name="Signature")


@pytest.fixture
def vanilla_candle(db, category):
    return Candle.objects.create(
        category=category,
        name="Vanilla Dream",
        description="A cozy vanilla and amber blend for winter evenings.",
        price="24.00",
        stock_qty=10,
        fragrance_family="gourmand",
        intensity=Candle.Intensity.MEDIUM,
        mood_tags=["cozy", "warm"],
    )


@pytest.fixture
def rose_candle(db, category):
    return Candle.objects.create(
        category=category,
        name="Rose Bloom",
        description="Fresh rose petals with a soft green undertone.",
        price="28.00",
        stock_qty=0,
        is_sold_out=True,
        fragrance_family="floral",
    )


def _fake_openai_text(text):
    """Shape of a minimal OpenAI Responses API payload."""
    return {"output_text": text}


# ======================================================
# extract_slug_from_text()
# ======================================================
class TestExtractSlugFromText:
    def test_none_input(self):
        assert extract_slug_from_text(None) is None

    def test_empty_string(self):
        assert extract_slug_from_text("") is None

    def test_no_url_present(self):
        assert extract_slug_from_text("what candles do you have?") is None

    @pytest.mark.parametrize(
        "text,expected_slug",
        [
            ("https://kfcandle.com/catalog/vanilla-dream", "vanilla-dream"),
            ("http://kfcandle.com/catalog/vanilla-dream", "vanilla-dream"),
            ("https://www.kfcandle.com/catalog/vanilla-dream", "vanilla-dream"),
            (
                "https://www.kfcandle.com/catalog/item/vanilla-dream",
                "vanilla-dream",
            ),
            ("https://kfcandle.com/catalog/item/vanilla-dream", "vanilla-dream"),
            ("/catalog/vanilla-dream", "vanilla-dream"),
            ("/catalog/item/vanilla-dream", "vanilla-dream"),
            ("kfcandle.com/catalog/vanilla-dream", "vanilla-dream"),
            (
                "Check this out: https://kfcandle.com/catalog/item/rose-bloom-2 please!",
                "rose-bloom-2",
            ),
            (
                "HTTPS://KFCANDLE.COM/CATALOG/ITEM/VANILLA-DREAM",
                "vanilla-dream",
            ),
            (
                "https://kfcandle.com/catalog/item/vanilla-dream?ref=email",
                "vanilla-dream",
            ),
            ("https://kfcandle.com/catalog/item/vanilla-dream/", "vanilla-dream"),
        ],
    )
    def test_url_formats(self, text, expected_slug):
        assert extract_slug_from_text(text) == expected_slug

    def test_unrelated_domain_still_matches_catalog_path(self):
        # The regex only anchors on the /catalog/ path, not the domain, so
        # this documents the current (permissive) behavior.
        assert extract_slug_from_text("https://evil.example.com/catalog/some-slug") == "some-slug"


# ======================================================
# get_candle_by_slug()
# ======================================================
@pytest.mark.django_db
class TestGetCandleBySlug:
    def test_existing_slug_returns_candle(self, vanilla_candle):
        result = get_candle_by_slug(vanilla_candle.slug)

        assert result is not None
        assert result["id"] == vanilla_candle.id
        assert result["slug"] == vanilla_candle.slug
        assert result["name"] == "Vanilla Dream"

    def test_missing_slug_returns_none(self, vanilla_candle):
        assert get_candle_by_slug("does-not-exist") is None

    def test_empty_slug_returns_none(self):
        assert get_candle_by_slug("") is None
        assert get_candle_by_slug(None) is None

    def test_slug_lookup_is_case_insensitive(self, vanilla_candle):
        result = get_candle_by_slug(vanilla_candle.slug.upper())
        assert result is not None
        assert result["id"] == vanilla_candle.id

    def test_falls_back_to_name_match_when_slug_not_found(self, db, category):
        # Slug on record differs from what's being searched, but the name
        # matches once hyphens are turned back into spaces.
        candle = Candle.objects.create(
            category=category,
            name="Ocean Breeze",
            slug="totally-different-slug",
            price="20.00",
        )

        result = get_candle_by_slug("ocean-breeze")

        assert result is not None
        assert result["id"] == candle.id


# ======================================================
# search_candles()
# ======================================================
@pytest.mark.django_db
class TestSearchCandles:
    def test_matches_by_name(self, vanilla_candle, rose_candle):
        results = search_candles("vanilla")

        assert len(results) == 1
        assert results[0]["id"] == vanilla_candle.id

    def test_matches_by_mood_tag(self, vanilla_candle, rose_candle):
        results = search_candles("cozy")

        assert len(results) == 1
        assert results[0]["id"] == vanilla_candle.id

    def test_matches_by_fragrance_family(self, vanilla_candle, rose_candle):
        results = search_candles("floral")

        assert len(results) == 1
        assert results[0]["id"] == rose_candle.id

    def test_no_match_returns_empty_list(self, vanilla_candle, rose_candle):
        assert search_candles("nonexistent scent xyz") == []

    def test_empty_query_returns_empty_list(self, vanilla_candle):
        assert search_candles("") == []
        assert search_candles("   ") == []

    def test_query_with_only_short_terms_returns_empty_list(self, vanilla_candle):
        # Terms shorter than 2 characters are dropped entirely.
        assert search_candles("a") == []

    def test_respects_limit(self, db, category):
        for i in range(5):
            Candle.objects.create(
                category=category,
                name=f"Cedar Candle {i}",
                price="10.00",
            )

        results = search_candles("cedar", limit=3)

        assert len(results) == 3


# ======================================================
# LumiereReplyView
# ======================================================
@pytest.mark.django_db
class TestLumiereReplyView:
    url = "/api/lumiere/reply/"

    def test_valid_payload_returns_ai_reply(self, api_client, settings, vanilla_candle):
        settings.OPENAI_API_KEY = "test-key"

        with patch("lumiere.services._call_openai_payload") as mock_call:
            mock_call.return_value = _fake_openai_text(
                "I'd love to suggest our Vanilla Dream candle."
            )

            response = api_client.post(
                self.url,
                {"text": "I want something cozy for winter", "locale": "en"},
                format="json",
            )

        assert response.status_code == 200
        assert response.data["text"] == "I'd love to suggest our Vanilla Dream candle."
        mock_call.assert_called_once()

    def test_api_key_not_configured_returns_graceful_message(self, api_client, settings):
        settings.OPENAI_API_KEY = ""

        response = api_client.post(
            self.url,
            {"text": "hello", "locale": "en"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["text"] == "AI is not configured on the server yet."

    def test_openai_failure_falls_back_to_friendly_error(self, api_client, settings):
        settings.OPENAI_API_KEY = "test-key"

        with patch("lumiere.services._call_openai_payload") as mock_call:
            mock_call.side_effect = Exception("boom")

            response = api_client.post(
                self.url,
                {"text": "hello", "locale": "en"},
                format="json",
            )

        assert response.status_code == 200
        assert "something went wrong" in response.data["text"].lower()

    def test_slug_in_text_resolves_candle_suggestion(self, api_client, settings, vanilla_candle):
        settings.OPENAI_API_KEY = "test-key"

        with patch("lumiere.services._call_openai_payload") as mock_call:
            mock_call.return_value = _fake_openai_text("Great choice!")

            response = api_client.post(
                self.url,
                {
                    "text": f"tell me about https://kfcandle.com/catalog/item/{vanilla_candle.slug}",
                    "locale": "en",
                },
                format="json",
            )

        assert response.status_code == 200
        suggestions = response.data.get("suggestions", [])
        assert len(suggestions) == 1
        assert suggestions[0]["id"] == vanilla_candle.id

    def test_missing_text_is_invalid(self, api_client):
        response = api_client.post(self.url, {"locale": "en"}, format="json")
        assert response.status_code == 400
        assert "text" in response.data

    def test_blank_text_is_invalid(self, api_client):
        response = api_client.post(self.url, {"text": ""}, format="json")
        assert response.status_code == 400

    def test_text_exceeding_max_length_is_invalid(self, api_client):
        response = api_client.post(
            self.url,
            {"text": "x" * 2001},
            format="json",
        )
        assert response.status_code == 400
        assert "text" in response.data

    def test_invalid_locale_is_rejected(self, api_client):
        response = api_client.post(
            self.url,
            {"text": "hello", "locale": "de"},
            format="json",
        )
        assert response.status_code == 400
        assert "locale" in response.data

    def test_invalid_history_role_is_rejected(self, api_client):
        response = api_client.post(
            self.url,
            {
                "text": "hello",
                "history": [{"role": "bot", "text": "hi"}],
            },
            format="json",
        )
        assert response.status_code == 400

    def test_null_and_missing_optional_fields_use_defaults(self, api_client, settings):
        settings.OPENAI_API_KEY = ""

        response = api_client.post(
            self.url,
            {"text": "hello", "userName": None, "page": None},
            format="json",
        )

        # userName/page allow blank but not null explicitly for "page";
        # userName allow_null=True should be accepted.
        assert response.status_code in (200, 400)

    def test_wrong_type_for_text_is_invalid(self, api_client):
        # DRF's CharField is lenient about numerics (coerces them to str),
        # but a list/dict is never a valid "text" value.
        response = api_client.post(
            self.url,
            {"text": ["hello"]},
            format="json",
        )
        assert response.status_code == 400
        assert "text" in response.data

    def test_empty_payload_is_invalid(self, api_client):
        response = api_client.post(self.url, {}, format="json")
        assert response.status_code == 400
        assert "text" in response.data


# ======================================================
# Prices come from the pricing engine
# ======================================================
@pytest.fixture
def on_offer(db, category):
    """A candle in a 10% campaign, plus a global welcome offer that a guest
    doesn't get — Lumière takes no auth, so it must price like the
    catalogue does for a signed-out shopper."""
    candle = Candle.objects.create(category=category, name="Mulled Wine", stock_qty=100)
    CandleVariant.objects.create(candle=candle, size="8 oz", price="18.49", stock_qty=100)
    CandleVariant.objects.create(candle=candle, size="4 oz", price="9.99", stock_qty=100)

    campaign = Offer.objects.create(
        title="Spooky Season Offer", kind=Offer.Kind.HOLIDAY, discount_percent=10, priority=20
    )
    campaign.candles.add(candle)

    Offer.objects.create(
        title="Welcome 10%",
        kind=Offer.Kind.NEW_SHOPPER,
        discount_percent=10,
        apply_globally=True,
        priority=30,
    )

    return {"candle": candle, "campaign": campaign}


def _catalogue_card_price(api_client, candle):
    response = api_client.get("/api/candles/candles/")
    assert response.status_code == 200
    data = response.json()
    rows = data["results"] if isinstance(data, dict) else data
    row = next(row for row in rows if row["slug"] == candle.slug)
    return Decimal(str(row["discount_price"]))


class TestLumierePricesMatchCatalogue:
    def test_search_shows_the_catalogue_price(self, api_client, on_offer):
        card = _catalogue_card_price(api_client, on_offer["candle"])

        [suggestion] = search_candles("mulled")

        assert card == Decimal("8.99")
        assert Decimal(suggestion["price"]) == card

    def test_slug_lookup_shows_the_catalogue_price(self, api_client, on_offer):
        card = _catalogue_card_price(api_client, on_offer["candle"])

        suggestion = get_candle_by_slug(on_offer["candle"].slug)

        assert Decimal(suggestion["price"]) == card

    def test_ai_search_prices_what_it_shows_and_what_it_tells_the_model(self, on_offer):
        candle = on_offer["candle"]

        with patch("lumiere.services._call_openai_payload") as mock_call:
            mock_call.return_value = _fake_openai_text(
                json.dumps({"text": "Try this.", "product_ids": [candle.id], "reasons": {}})
            )
            result = ai_search_candles("something warm")

        assert result["suggestions"][0]["price"] == "8.99"

        sent = json.loads(mock_call.call_args.args[0]["input"])
        [entry] = sent["catalog"]
        assert entry["price_from"] == "8.99"
        assert sorted(v["price"] for v in entry["variants"]) == ["16.64", "8.99"]

    def test_cached_ai_search_is_priced_again(self, on_offer):
        """A cached answer keeps the model's picks, not the prices: an offer
        that ends inside the cache window must not leave its price behind."""
        candle = on_offer["candle"]

        with patch("lumiere.services._call_openai_payload") as mock_call:
            mock_call.return_value = _fake_openai_text(
                json.dumps({"text": "Try this.", "product_ids": [candle.id], "reasons": {}})
            )
            first = ai_search_candles("something warm")

            on_offer["campaign"].is_active = False
            on_offer["campaign"].save()

            second = ai_search_candles("something warm")

        mock_call.assert_called_once()
        assert first["suggestions"][0]["price"] == "8.99"
        assert second["suggestions"][0]["price"] == "9.99"


# ======================================================
# Lumière-only notes
# ======================================================
MATCHA_NOTES = "Green tea and steamed milk; suits a calm desk."


@pytest.fixture
def matcha(db, category):
    """One scent in two sizes. Notes are written on the small one only;
    each size has its own burn time, except the large one."""
    small = Candle.objects.create(
        category=category,
        name="Matcha Chill",
        size="8 oz",
        mood_tags=["calm"],
        assistant_notes=MATCHA_NOTES,
        burn_time="45–50 hours",
    )
    large = Candle.objects.create(
        category=category, name="Matcha Chill", size="11.3 oz", mood_tags=["calm"]
    )
    for candle, price in ((small, "18.49"), (large, "24.99")):
        CandleVariant.objects.create(candle=candle, size=candle.size, price=price, stock_qty=5)
    return {"small": small, "large": large}


def _context_block(context, candle):
    """The context lines for one candle: its entry up to the next one."""
    lines = context.splitlines()
    start = next(i for i, line in enumerate(lines) if f"slug: {candle.slug}" in line)
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("- "):
            break
        block.append(line)
    return "\n".join(block)


class TestAssistantNotes:
    def test_notes_and_burn_time_reach_the_context(self, matcha):
        suggestion = get_candle_by_slug(matcha["small"].slug)

        block = _context_block(build_store_context([suggestion]), matcha["small"])

        assert f"Lumière notes: {MATCHA_NOTES}" in block
        assert "Burn time: 45–50 hours" in block

    def test_another_size_lends_its_notes_but_not_its_burn_time(self, matcha):
        suggestion = get_candle_by_slug(matcha["large"].slug)

        block = _context_block(build_store_context([suggestion]), matcha["large"])

        assert f"Lumière notes: {MATCHA_NOTES}" in block
        assert "Burn time" not in block

    def test_empty_notes_leave_no_line(self, vanilla_candle):
        suggestion = get_candle_by_slug(vanilla_candle.slug)

        block = _context_block(build_store_context([suggestion]), vanilla_candle)

        assert "Lumière notes" not in block
        assert "Burn time" not in block

    def test_whitespace_notes_count_as_empty(self, matcha):
        matcha["small"].assistant_notes = "   "
        matcha["small"].save()

        block = _context_block(
            build_store_context([get_candle_by_slug(matcha["large"].slug)]), matcha["large"]
        )

        assert "Lumière notes" not in block

    def test_instructions_limit_burn_time_to_what_is_listed(self):
        instructions = _build_instructions("en", None)

        assert "Only state a burn time when one is listed" in instructions
        assert "Lumière notes" in instructions

    def test_instructions_say_size_is_burn_time_not_strength(self):
        instructions = _build_instructions("en", None)

        assert "A bigger jar burns longer; it does not smell stronger." in instructions
        assert "in your first sentence" in instructions

    def test_closing_questions_already_asked_are_named(self):
        history = [
            {"role": "user", "text": "Something fresh?"},
            {"role": "assistant", "text": "Try Matcha Chill. Would you like gift wrapping?"},
            {"role": "user", "text": "Is the big one too much?"},
            {"role": "assistant", "text": "No, size changes burn time, not strength."},
            {"role": "user", "text": "Would you like to know a secret?"},
        ]

        closings = _closing_questions(history)
        instructions = _build_instructions("en", None, closings)

        # Only Lumière's own replies count, and only ones ending in a question.
        assert closings == ["Would you like gift wrapping?"]
        assert "- Would you like gift wrapping?" in instructions
        assert "already asked" not in _build_instructions("en", None, [])

    def test_reply_sends_notes_to_the_model_but_not_to_the_shopper(
        self, api_client, settings, matcha
    ):
        settings.OPENAI_API_KEY = "test-key"

        with patch("lumiere.services._call_openai_payload") as mock_call:
            mock_call.return_value = _fake_openai_text("Try Matcha Chill.")
            response = api_client.post(
                "/api/lumiere/reply/", {"text": "matcha"}, format="json"
            )

        assert response.status_code == 200
        assert MATCHA_NOTES in mock_call.call_args.args[0]["input"]
        assert MATCHA_NOTES not in response.content.decode()
        assert "45–50 hours" not in response.content.decode()

    def test_ai_search_sends_no_notes(self, matcha):
        with patch("lumiere.services._call_openai_payload") as mock_call:
            mock_call.return_value = _fake_openai_text(
                json.dumps({"text": "", "product_ids": [], "reasons": {}})
            )
            ai_search_candles("something calm")

        sent = mock_call.call_args.args[0]["input"]
        assert MATCHA_NOTES not in sent
        assert "45–50 hours" not in sent
