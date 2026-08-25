import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { Candle, CandleBadge } from "../types/candle";
import {
  getDisplayPrice,
  getLowestActiveVariant,
  isCandleAvailable,
} from "../types/candle";

import { listCandles } from "../api/candles";
import { useAppDispatch } from "../store/hooks";
import { openSizeModal } from "../store/modalSlice";

import "../styles/Catalog.css";
import "../styles/Promo.css";

/**
 * Slug of the badge set in the admin panel. Any candle carrying this badge
 * appears on this page. Change it here if the slug in the admin differs.
 */
const PROMO_BADGE_SLUG = "buy-2-get-3";

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
    rule: "One promotion at a time",
    detail:
      "This offer cannot be combined with any other discount, promo code or gift-card promotion.",
  },
  {
    rule: "Eligible candles only",
    detail:
      "Candles that are already discounted or part of another campaign do not qualify. Only the candles shown on this page are eligible.",
  },
  {
    rule: "The free candle",
    detail:
      "Add three eligible candles to your cart. The lowest-priced of the three is free — the discount is applied automatically at checkout.",
  },
  {
    rule: "While stocks last",
    detail:
      "The offer runs until the eligible candles sell out. Sold-out items cannot be substituted.",
  },
  {
    rule: "Returns",
    detail:
      "If you return part of a promotional set, the free candle is re-priced at its regular value and deducted from the refund.",
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
            Buy 2, Get 3
          </h1>
          <p className="promo__subtitle">
            Choose any three candles from the selection below and the
            lowest-priced one is on us.
          </p>
        </header>

        <section className="promo__terms" aria-labelledby="promo-terms-title">
          <h2 id="promo-terms-title" className="promo__termsTitle">
            How it works
          </h2>

          <table className="promo__table">
            <caption className="promo__tableCaption">
              Offer conditions
            </caption>
            <tbody>
              {TERMS.map((item) => (
                <tr key={item.rule}>
                  <th scope="row">{item.rule}</th>
                  <td>{item.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="promo__products" aria-labelledby="promo-products-title">
          <h2 id="promo-products-title" className="promo__sectionTitle">
            Candles in this offer
          </h2>

          {loading ? (
            <p className="promo__state">Loading…</p>
          ) : error ? (
            <p className="promo__state promo__state--error">{error}</p>
          ) : eligible.length === 0 ? (
            <div className="promo__empty">
              <p>
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
                          sizes="(max-width: 640px) 100vw, (max-width: 1200px) 50vw, 33vw"
                          alt={product.name}
                          loading={isPriority ? "eager" : "lazy"}
                          fetchPriority={isPriority ? "high" : "auto"}
                          decoding="async"
                          width={900}
                          height={600}
                        />

                        <div className="catalogCard__badges">
                          {!available ? (
                            <span className="badge badge--soldout">
                              {t("catalog.soldOut")}
                            </span>
                          ) : (
                            <span className="badge badge--promo">
                              Buy 2, Get 3
                            </span>
                          )}
                        </div>
                      </div>
                    </Link>

                    <div className="catalogCard__body">
                      <div className="catalogCard__metaRow">
                        <Link to={destination} className="catalogCard__titleLink">
                          <h3 className="catalogCard__name">{product.name}</h3>
                        </Link>

                        <div className="catalogCard__price">
                          {displayPrice ? `$${displayPrice}` : "Select size"}
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