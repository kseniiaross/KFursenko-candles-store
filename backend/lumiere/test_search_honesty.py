"""The catalogue search says no before it offers the closest candle.

Asked for a pineapple candle, it used to offer Mango Island as "reminiscent
of pineapple" rather than say the shop has none. A mango candle doesn't
smell of pineapple, and a shopper who buys it expecting one sends it back.
The search prompt carries the rule the assistant already follows on
discounts: say what is, don't invent what isn't. When no candle is what
was asked for, the first sentence says so, and the closest is offered as
the closest.

TestLive* asks the real model: LUMIERE_LIVE=1 pytest lumiere/test_search_honesty.py
"""

import json
import re
from unittest.mock import patch

import pytest
from django.core.cache import cache

from candles.models import Candle, CandleVariant, Category
from lumiere import services
from lumiere.test_lumiere import _fake_openai_text
from lumiere.test_offers_context import live, live_model  # noqa: F401

SEARCH_URL = "/api/lumiere/search/"


@pytest.fixture
def tropical_shop(db):
    """A tropical candle, a green one and a spiced one; nothing pineapple."""
    single_wick = Category.objects.create(name="Single-wick candles")
    candles = {
        "Mango Island": "Ripe mango and tropical fruit over creamy coconut and warm vanilla. Bright, juicy and sunny.",
        "Matcha Chill": "Green matcha tea with soft jasmine and a clean, calm finish.",
        "Spice Delight": "Pumpkin, cinnamon and nutmeg over creamy vanilla. Warm autumn comfort.",
    }
    for name, description in candles.items():
        candle = Candle.objects.create(category=single_wick, name=name, size="8 oz", description=description)
        CandleVariant.objects.create(candle=candle, size="8 oz", price="18.49", stock_qty=10)
    return candles


@pytest.mark.django_db
def test_the_rule_is_in_the_search_prompt(tropical_shop):
    """Runs in CI: a prompt tidied without the rule fails here, before
    anyone has to ask the real model."""
    with patch("lumiere.services._call_openai_payload") as mock_call:
        mock_call.return_value = _fake_openai_text(
            json.dumps({"text": "", "product_ids": [], "reasons": {}})
        )
        services.ai_search_candles("pineapple")

    instructions = mock_call.call_args.args[0]["instructions"]
    assert "the first sentence of text says plainly that the shop has no such candle" in instructions
    assert "offer the closest as the closest" in instructions
    assert "never say or suggest it smells of, contains or resembles what was asked for" in instructions


# The first sentence names the thing and says the shop has none of it.
DENIES = {
    "en": ("pineapple", r"\b(no|not|don't|doesn't|isn't|aren't)\b"),
    "ru": ("ананас", r"\b(нет|не)\b"),
    "es": ("piña", r"\b(no|ninguna)\b"),
    "fr": ("ananas", r"\b(n'|ne|pas|aucune?)\b|\bn'"),
}


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]


@live
@pytest.mark.django_db
class TestLiveNoPineapple:
    """Three asks each: one good answer at temperature 0.25 proves little."""

    @pytest.mark.parametrize("locale", ["en", "ru", "es", "fr"])
    def test_says_there_is_none_in_the_first_sentence(self, tropical_shop, api_client, live_model, locale):
        thing, denial = DENIES[locale]

        for _ in range(3):
            # The search caches the model's picks; every ask must reach it.
            cache.clear()
            body = api_client.post(SEARCH_URL, {"query": thing, "locale": locale}, format="json").json()
            first = _first_sentence(body["text"])
            print(f"\n[{locale}, {thing}]", body["text"], [s["name"] for s in body["suggestions"]])

            assert thing in first.lower(), first
            assert re.search(denial, first, re.I), first
