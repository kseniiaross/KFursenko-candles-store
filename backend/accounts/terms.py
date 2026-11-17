"""The terms of the sign-up discount, as the shopper accepts them on Register.

The wording is the sign-up modal's (discountModal.terms and termsNoLimit in
frontend/src/i18n.ts, kept identical by accounts/test_terms.py). The server
renders it, with the running offer's percent and days, so what is stored is
exactly what the page showed: a page left open across a change to the
wording or the offer sends an old version and is given the new text to
accept, never a record of words it didn't show.
"""

import hashlib
from typing import Optional, TypedDict

from orders.discounts import active_welcome_offer

LOCALES = ("en", "ru", "es", "fr")

# (with the days limit, without it), in i18next's {{name}} syntax.
TEMPLATES = {
    "en": (
        'Create an account and {{percent}}% comes off your first order automatically at checkout — no code needed. Valid for {{days}} days after sign-up. It applies to everything in your basket except candles already on sale, which keep their sale price, and the candles that pay for a free one in Buy 2, Get 3. Not applied to shipping or tax.',
        'Create an account and {{percent}}% comes off your first order automatically at checkout — no code needed. It applies to everything in your basket except candles already on sale, which keep their sale price, and the candles that pay for a free one in Buy 2, Get 3. Not applied to shipping or tax.',
    ),
    "ru": (
        'Зарегистрируйтесь — и скидка {{percent}}% автоматически применится к первому заказу, без промокода. Действует {{days}} дн. после регистрации. Скидка действует на всё в корзине, кроме свечей, которые уже продаются со скидкой (у них остаётся своя цена), и свечей, за которые в акции «Купи 2 — получи 3» положена бесплатная. На доставку и налог не распространяется.',
        'Зарегистрируйтесь — и скидка {{percent}}% автоматически применится к первому заказу, без промокода. Скидка действует на всё в корзине, кроме свечей, которые уже продаются со скидкой (у них остаётся своя цена), и свечей, за которые в акции «Купи 2 — получи 3» положена бесплатная. На доставку и налог не распространяется.',
    ),
    "es": (
        'Crea una cuenta y el {{percent}}% se descontará automáticamente de tu primer pedido al finalizar la compra, sin código. Válido durante {{days}} días tras el registro. Se aplica a todo el carrito salvo a las velas ya rebajadas, que mantienen su precio de oferta, y a las velas que pagan la vela gratis en Compra 2, llévate 3. No se aplica al envío ni a los impuestos.',
        'Crea una cuenta y el {{percent}}% se descontará automáticamente de tu primer pedido al finalizar la compra, sin código. Se aplica a todo el carrito salvo a las velas ya rebajadas, que mantienen su precio de oferta, y a las velas que pagan la vela gratis en Compra 2, llévate 3. No se aplica al envío ni a los impuestos.',
    ),
    "fr": (
        "Créez un compte et {{percent}}% seront déduits automatiquement de votre première commande lors du paiement, sans code. Valable {{days}} jours après l'inscription. La remise s'applique à tout le panier, sauf aux bougies déjà en promotion, qui gardent leur prix promotionnel, et aux bougies qui font gagner la bougie offerte dans « 2 achetées, 1 offerte ». Elle ne s'applique ni à la livraison ni aux taxes.",
        "Créez un compte et {{percent}}% seront déduits automatiquement de votre première commande lors du paiement, sans code. La remise s'applique à tout le panier, sauf aux bougies déjà en promotion, qui gardent leur prix promotionnel, et aux bougies qui font gagner la bougie offerte dans « 2 achetées, 1 offerte ». Elle ne s'applique ni à la livraison ni aux taxes.",
    ),
}


class Terms(TypedDict):
    version: str
    locale: str
    text: str
    # For Register's line about the discount, so it never names another
    # figure than the terms. Not part of the record: the text already says it.
    percent: int


def normalize_locale(value: Optional[str]) -> str:
    locale = (value or "").strip().lower()[:2]
    return locale if locale in LOCALES else "en"


def current_terms(locale: Optional[str]) -> Optional[Terms]:
    """The terms a new account accepts now, in the shopper's language, or
    None when no sign-up discount is running and there is nothing to agree
    to. The version is the text's own hash: any change to the wording, the
    percent or the days is a new version."""
    offer = active_welcome_offer()

    if offer is None:
        return None

    locale = normalize_locale(locale)
    with_days, no_limit = TEMPLATES[locale]
    days = offer.new_shopper_days_active

    text = (with_days if days else no_limit).replace(
        "{{percent}}", str(offer.discount_percent)
    ).replace("{{days}}", str(days or ""))

    return {
        "version": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "locale": locale,
        "text": text,
        "percent": offer.discount_percent,
    }
