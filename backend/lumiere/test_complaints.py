"""An upset shopper: where Lumière sends them, and what it can't offer.

Lumière can't pass anything on, so it points to the address on the Contacts
page. And a shopper who says they have already ordered can't have the
sign-up discount, which ends with a new account's first paid order. The
model is told it runs but isn't theirs, without the terms to sell it with,
so it can't be offered as a make-good.

TestLive* asks the real model: LUMIERE_LIVE=1 pytest lumiere/test_complaints.py
"""

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from lumiere import services
from lumiere.test_offers_context import REPLY_URL, live, live_model, shop  # noqa: F401

CONTACT_TS = Path(__file__).resolve().parents[2] / "frontend/src/constants/contact.ts"


def test_points_to_the_address_on_the_contacts_page():
    shown = re.search(r'SUPPORT_EMAIL = "([^"]+)"', CONTACT_TS.read_text()).group(1)

    assert services.SHOP_CONTACT_EMAIL == shown
    assert shown in services._build_instructions("en", None)


PLACED_AN_ORDER = [
    # The pressure-test complaints.
    "Your site broke twice at checkout, my order showed up a week late, and I wasted an hour.",
    "Сайт дважды сломался при оформлении, заказ пришёл на неделю позже, я потратила целый час.",
    "My order never arrived.",
    "My last order was damaged.",
    "I've ordered from you before.",
    "I already bought three candles here.",
    "Мой заказ так и не пришёл.",
    "Я уже заказывала у вас.",
    "Mi pedido llegó tarde.",
    "Ma commande est arrivée en retard.",
]

NOT_YET = [
    "Do I get the discount on my first order?",
    "Получу ли я скидку на первый заказ?",
    "Будет ли скидка на мой первый заказ?",
    "If I order two candles, do I get a third free?",
    "How long will my order take to arrive?",
    "When will my order arrive?",
    "Can I order today and have it by Friday?",
    "¿Tengo descuento en mi primer pedido?",
    "Est-ce que j'ai une réduction sur ma première commande ?",
]


@pytest.mark.parametrize("text", PLACED_AN_ORDER)
def test_a_shopper_who_says_they_ordered(text):
    assert services.mentions_a_placed_order([text])


@pytest.mark.parametrize("text", NOT_YET)
def test_a_shopper_who_has_not_said_so(text):
    assert not services.mentions_a_placed_order([text])


def _model_input(api_client, text, history=None):
    with patch.object(services, "_call_openai_payload") as call:
        call.return_value = {"output_text": "Ok."}
        api_client.post(REPLY_URL, {"text": text, "history": history or []}, format="json")

    return call.call_args.args[0]["input"]


@pytest.mark.django_db
class TestSignUpOfferInTheContext:
    @pytest.fixture(autouse=True)
    def key(self, settings):
        settings.OPENAI_API_KEY = "test-key"

    def test_a_new_shopper_asking_about_their_first_order_still_gets_it(self, shop, api_client):
        model_input = _model_input(api_client, "Do I get the discount on my first order?")

        assert "New Shopper" in model_input and "10%" in model_input

    def test_not_theirs_for_a_shopper_whose_order_was_late(self, shop, api_client):
        model_input = _model_input(
            api_client, "My order showed up a week late. I want a discount to make up for it."
        )

        assert "This shopper has said they already placed an order" in model_input
        # Named, but without the terms to sell it with.
        assert "10%" not in model_input
        assert "The sign-up discount with" not in model_input
        # The other offers are untouched.
        assert "Autumn Sale" in model_input and "Spring B2G3" in model_input

    def test_not_theirs_when_the_order_came_up_earlier_in_the_chat(self, shop, api_client):
        history = [{"role": "user", "text": "Заказ пришёл на неделю позже."}]

        model_input = _model_input(api_client, "Последний шанс. Да или нет?", history)

        assert "This shopper has said they already placed an order" in model_input


def _converse(api_client, turns, locale="en"):
    history, conversation, replies = [], "", []

    for turn in turns:
        body = api_client.post(
            REPLY_URL,
            {"text": turn, "locale": locale, "history": history, "conversation": conversation},
            format="json",
        ).json()
        conversation = body["conversation"]
        history += [
            {"role": "user", "text": turn},
            {"role": "assistant", "text": body["text"], "signature": body["signature"]},
        ]
        replies.append(body["text"])

    return replies


@live
@pytest.mark.django_db
class TestLiveReturningShopper:
    """Three asks each: one good answer at temperature 0.65 proves little."""

    def test_the_sign_up_discount_still_exists_for_new_accounts(self, shop, api_client, live_model):
        turns = [
            "I've ordered from you before, my last order arrived in October.",
            "Is there a discount for new customers?",
        ]

        for _ in range(3):
            text = _converse(api_client, turns)[-1]
            print("\n[returning, new-customer discount]", text)

            assert re.search(r"\bnew (account|customer|shopper)s?\b", text, re.I)
            assert re.search(r"\bdiscount\b", text, re.I)
            assert not re.search(
                r"no (sign-up |new.customer )?discount|isn.t (running|available right now)"
                r"|not running|no offers",
                text,
                re.I,
            )
