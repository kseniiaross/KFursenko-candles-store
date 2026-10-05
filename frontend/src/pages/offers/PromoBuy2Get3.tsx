import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { Candle, CandleBadge } from "../../types/candle";
import {
  getDisplayPrice,
  getLowestActiveVariant,
  isCandleAvailable,
} from "../../types/candle";

import { listCandles } from "../../api/candles";
import Price from "../../components/Price";
import { useAppDispatch } from "../../store/hooks";
import { openSizeModal } from "../../store/modalSlice";

import "../../styles/Catalog.css";
import "../../styles/offers/PromoBuy2Get3.css";

/**
 * Slug of the badge set in the admin panel. Any candle carrying this badge
 * appears on this page. Change it here if the slug in the admin differs.
 */
const PROMO_BADGE_SLUG = "buy-two-get-three";

function buildOptimizedImageUrl(url: string, width: number): string {
  if (!url) return "";

  if (url.includes("res.cloudinary.com") && url.includes("/upload/")) {
    if (url.includes("/upload/f_auto") || url.includes("/upload/q_auto")) {
      return url;
    }
    return url.replace("/upload/", `/upload/f_auto,q_auto,w_${width}/`);
  }

  return url;
}

function hasPromoBadge(candle: Candle): boolean {
  const badges: CandleBadge[] = Array.isArray(candle.badges) ? candle.badges : [];
  return badges.some((badge) => badge.slug === PROMO_BADGE_SLUG);
}

const TERMS: Array<{ rule: string; detail: string }> = [
  {
    rule: "How it works",
    detail:
      "Add two of the large candles below to your basket and a small candle comes free. Buy four and two come free, and so on.",
  },
  {
    rule: "Which candles are free",
    detail:
      "The free candle is one of the 8 oz Spring scents — Mango Island, Matcha Chill, Sweet Lemon Dew or Tidal Bore. You choose which one when the offer is ready.",
  },
  {
    rule: "Which candles qualify",
    detail:
      "The 11.3 oz Spring candles shown on this page. They carry the offer badge in the catalogue. Small candles do not count towards the two.",
  },
  {
    rule: "No code needed",
    detail:
      "The discount is applied at checkout. Your basket will show the free candle at $0.00 before you pay.",
  },
  {
    rule: "One promotion at a time",
    detail:
      "This offer does not combine with other discounts. A candle already in a seasonal campaign keeps that campaign's price and cannot be the free one.",
  },
  {
    rule: "While stocks last",
    detail:
      "The offer runs until the eligible candles sell out. Sold-out candles cannot be substituted.",
  },
  {
    rule: "Returns",
    detail:
      "If you return part of a promotional set and the remaining candles no longer qualify, the free candle is charged at its regular price and deducted from the refund.",
  },
];

const PromoBuy2Get3: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();

  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      try {
        setLoading(true);
        setError("");

        const data = await listCandles({ ordering: "-created_at" });
        if (!active) return;

        setCandles(data.filter(hasPromoBadge));
      } catch {
        if (!active) return;
        setError(t("catalog.loadError"));
      } finally {
        if (active) setLoading(false);
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [t]);

  const eligible = useMemo(() => candles, [candles]);

  const onAddToCart = (candle: Candle): void => {
    if (!getLowestActiveVariant(candle)) return;
    dispatch(openSizeModal(candle));
  };

  return (
    <main className="promo" aria-labelledby="promo-title">
      <div className="promo__inner">
        <header className="promo__header">
          <p className="promo__kicker">Offers</p>
          <h1 id="promo-title" className="promo__title">
            Buy Two, Get Three
          </h1>
          <p className="promo__lead">
            Take two of our large Spring candles and a small one is on us.
            Nothing to enter at checkout — the free candle is already at zero
            when you pay.
          </p>
        </header>

        <div className="promo__highlight" role="note">
          <span className="promo__highlightLabel">The deal</span>
          <span className="promo__highlightValue">
            Two 11.3 oz candles earn one 8 oz candle free
          </span>
        </div>

        <section className="promo__terms" aria-labelledby="promo-terms-title">
          <h2 id="promo-terms-title" className="promo__sectionTitle">
            The details
          </h2>

          {/* A definition list rather than a table: these are rule-and-
              explanation pairs, not tabular data, and a table forces a
              two-column layout that collapses badly on a phone. */}
          <dl className="promo__termsList">
            {TERMS.map((item) => (
              <div key={item.rule} className="promo__term">
                <dt className="promo__termRule">{item.rule}</dt>
                <dd className="promo__termDetail">{item.detail}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section
          className="promo__products"
          aria-labelledby="promo-products-title"
        >
          <h2 id="promo-products-title" className="promo__sectionTitle">
            The candles that qualify
          </h2>

          {loading ? (
            <p className="promo__state">Loading…</p>
          ) : error ? (
            <p className="promo__state promo__state--error">{error}</p>
          ) : eligible.length === 0 ? (
            <div className="promo__empty">
              <p className="promo__emptyText">
                No candles are part of this offer right now. New eligible
                candles are added regularly.
              </p>
              <Link to="/catalog" className="promo__emptyLink">
                Browse the full catalog →
              </Link>
            </div>
          ) : (
            <div className="catalog__grid">
              {eligible.map((product, index) => {
                const coverUrl = product.image ?? "";
                if (!coverUrl) return null;

                const small = buildOptimizedImageUrl(coverUrl, 480);
                const medium = buildOptimizedImageUrl(coverUrl, 800);
                const large = buildOptimizedImageUrl(coverUrl, 1200);

                const destination = `/catalog/item/${product.slug}`;
                const available = isCandleAvailable(product);
                const displayPrice = getDisplayPrice(product);
                const firstVariant = getLowestActiveVariant(product);
                const isPriority = index === 0;

                const onSale =
                  displayPrice !== null &&
                  displayPrice !== undefined &&
                  product.discount_price !== null &&
                  product.discount_price !== undefined &&
                  Number(product.discount_price) < Number(displayPrice);

                return (
                  <article key={product.id} className="catalogCard">
                    <Link
                      to={destination}
                      className="catalogCard__imageLink"
                      aria-label={`Open ${product.name}`}
                    >
                      <div className="catalogCard__media">
                        <img
                          className="catalogCard__img"
                          src={medium}
                          srcSet={`${small} 480w, ${medium} 800w, ${large} 1200w`}
                          sizes="(max-width: 600px) 100vw, (max-width: 900px) 50vw, 25vw"
                          alt={product.name}
                          loading={isPriority ? "eager" : "lazy"}
                          fetchPriority={isPriority ? "high" : "auto"}
                          decoding="async"
                          width={1000}
                          height={1250}
                        />

                        <div className="catalogCard__badges">
                          {!available ? (
                            <span className="badge badge--soldout">
                              {t("catalog.soldOut")}
                            </span>
                          ) : (
                            <span className="badge badge--promo">
                              Buy Two Get Three
                            </span>
                          )}
                        </div>
                      </div>
                    </Link>

                    <div className="catalogCard__body">
                      <div
                        className={`catalogCard__metaRow${
                          onSale ? " catalogCard__metaRow--stacked" : ""
                        }`}
                      >
                        <Link
                          to={destination}
                          className="catalogCard__titleLink"
                        >
                          <h3 className="catalogCard__name">{product.name}</h3>
                        </Link>

                        <div className="catalogCard__price">
                          {displayPrice ? (
                            <Price
                              price={displayPrice}
                              discountPrice={product.discount_price}
                            />
                          ) : (
                            <span className="catalogCard__priceHint">
                              Select size
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="catalogCard__actions">
                        {!available ? (
                          <button type="button" className="catalogCard__btn">
                            {t("catalog.notifyMe")}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="catalogCard__btn"
                            onClick={() => onAddToCart(product)}
                            disabled={!firstVariant}
                          >
                            {t("catalog.addToCart")}
                          </button>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </main>
  );
};

export default PromoBuy2Get3;