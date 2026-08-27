import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { getCandleBySlug, getCollectionScentsBySlug } from "../api/candles";
import { addToCart as addToCartApi } from "../api/cart";
import { useAppDispatch, useAppSelector } from "../store/hooks";
import { addToCart, setCart } from "../store/cartSlice";

import type { Candle, CandleVariant } from "../types/candle";
import { getSizeOptions, hasColorChoice } from "../types/candle";

import "../styles/CatalogDetail.css";

/** Labels the description uses for its structured lines. Anything not
 *  listed here stays in the lead paragraph. */
const FACT_LABELS: Record<string, string> = {
  scent: "scent",
  notes: "scent",
  mood: "mood",
  "perfect for": "bestFor",
  "best for": "bestFor",
  details: "details",
};

const LABELLED_LINE = /^\s*([a-z][a-z\s]{1,20}?)\s*:\s*(.+)$/i;

type ParsedDescription = {
  lead: string;
  facts: Record<string, string[]>;
};

/** The description arrives as one blob with labelled lines inside, which
 *  is what made it read as a wall of text. Split it so those parts can
 *  become tags and rows instead. */
function parseDescription(description: string): ParsedDescription {
  const facts: Record<string, string[]> = {};
  const leadLines: string[] = [];

  for (const line of (description || "").split("\n")) {
    const match = line.match(LABELLED_LINE);
    const key = match ? FACT_LABELS[match[1].trim().toLowerCase()] : undefined;

    if (!match || !key) {
      leadLines.push(line);
      continue;
    }

    const values = match[2]
      .split(/[•·|]/)
      .map((value) => value.trim())
      .filter(Boolean);

    facts[key] = (facts[key] ?? []).concat(values);
  }

  return { lead: leadLines.join("\n").trim(), facts };
}

function uniqueTags(...groups: Array<string[] | undefined>): string[] {
  const seen = new Set<string>();

  for (const group of groups) {
    if (!Array.isArray(group)) continue;

    for (const tag of group) {
      const clean = String(tag).trim();
      if (clean) seen.add(clean);
    }
  }

  return [...seen];
}

const CatalogDetail: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { t, i18n } = useTranslation();

  const isLoggedIn = useAppSelector((state) => Boolean(state.auth?.isLoggedIn));

  const [item, setItem] = useState<Candle | null>(null);
  const [variant, setVariant] = useState<CandleVariant | null>(null);
  const [scents, setScents] = useState<Candle[]>([]);
  const [adding, setAdding] = useState(false);
  const [zoomImg, setZoomImg] = useState<string>("");

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      if (!slug) return;

      try {
        const data = await getCandleBySlug(slug);

        if (!active) return;

        setItem(data);

        const activeVariants = (data.variants ?? []).filter((v) => v.is_active);

        if (activeVariants.length > 0) {
          setVariant(activeVariants[0]);
        } else if (data.variants && data.variants.length > 0) {
          setVariant(data.variants[0]);
        } else {
          setVariant(null);
        }

        try {
          const siblings = await getCollectionScentsBySlug(slug);

          if (!active) return;

          setScents(siblings);
        } catch {
          if (!active) return;

          setScents([]);
        }
      } catch {
        if (!active) return;

        setItem(null);
        setVariant(null);
        setScents([]);
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [slug, i18n.language]);

  useEffect(() => {
    if (!zoomImg) return;

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        setZoomImg("");
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [zoomImg]);

  const price = useMemo(() => {
    if (!variant) return 0;
    return Number(variant.price) || 0;
  }, [variant]);

  const gallery = useMemo(() => {
    if (!item) return [];

    return [item.image ?? "", ...(item.images ?? []).map((img) => img.image)]
      .filter(Boolean)
      .filter((url, index, all) => all.indexOf(url) === index);
  }, [item]);

  const parsed = useMemo(
    () => parseDescription(item?.description ?? ""),
    [item?.description]
  );

  const buildCartItem = () => {
    if (!item || !variant) return null;

    const variantId = Number(variant.id);
    const candleId = Number(item.id);

    if (!variantId || !candleId) return null;

    return {
      variant_id: variantId,
      candle_id: candleId,
      name: item.name,
      price: Number(variant.price) || 0,
      image: item.image ?? undefined,
      size: variant.size,
      quantity: 1,
      isGift: false,
    };
  };

  const onAddToCart = async (): Promise<void> => {
    if (!item || !variant || adding) return;

    const cartItem = buildCartItem();

    if (!cartItem) return;

    setAdding(true);
    dispatch(addToCart(cartItem));

    try {
      if (!isLoggedIn) return;

      const serverItems = await addToCartApi({
        variant_id: cartItem.variant_id,
        quantity: 1,
        is_gift: false,
      });

      if (Array.isArray(serverItems) && serverItems.length > 0) {
        dispatch(setCart(serverItems));
      }
    } catch (error) {
      console.error("Failed to sync cart with backend:", error);
    } finally {
      setAdding(false);
    }
  };

  if (!item) return null;

  // Colors and sizes are separate products, so each switcher navigates
  // instead of mutating state — that is what makes the photos change
  // along with the choice.
  const showColors = hasColorChoice(item);
  const sizeOptions = getSizeOptions(item);
  const showSizes = sizeOptions.length > 1;

  // The structured JSON fields win when they are filled; the labelled
  // lines in the description are the fallback until they are.
  const scentNotes = uniqueTags(
    item.top_notes,
    item.heart_notes,
    item.base_notes
  );
  const notes = scentNotes.length > 0 ? scentNotes : parsed.facts.scent ?? [];

  const moodFromTags = uniqueTags(item.mood_tags);
  const mood = moodFromTags.length > 0 ? moodFromTags : parsed.facts.mood ?? [];

  const bestForFromTags = uniqueTags(item.use_case_tags, item.ideal_spaces);
  const bestFor =
    bestForFromTags.length > 0 ? bestForFromTags : parsed.facts.bestFor ?? [];

  const season = uniqueTags(item.season_tags);
  const details = parsed.facts.details ?? [];

  const rows: Array<{ key: string; label: string; values: string[] }> = [
    { key: "mood", label: t("catalogDetail.mood"), values: mood },
    { key: "bestFor", label: t("catalogDetail.bestFor"), values: bestFor },
    { key: "season", label: t("catalogDetail.season"), values: season },
    { key: "details", label: t("catalogDetail.details"), values: details },
  ].filter((row) => row.values.length > 0);

  return (
    <main className="catalogDetail" aria-label={t("catalogDetail.pageLabel")}>
      <div className="catalogDetail__inner">
        <div className="catalogDetail__layout">
          <section className="catalogDetail__gallery" aria-label={item.name}>
            {gallery.map((img, index) => (
              <button
                key={img}
                type="button"
                className="catalogDetail__frame"
                onClick={() => setZoomImg(img)}
                aria-label={`${t("catalogDetail.selectImage")}: ${item.name}`}
              >
                <img
                  src={img}
                  className="catalogDetail__img"
                  alt={index === 0 ? item.name : ""}
                  loading={index === 0 ? "eager" : "lazy"}
                  decoding="async"
                />
              </button>
            ))}
          </section>

          <section className="catalogDetail__info">
            <div className="catalogDetail__panel">
              {item.category && (
                <p className="catalogDetail__eyebrow">{item.category.name}</p>
              )}

              <h1 className="catalogDetail__title">{item.name}</h1>

                            <div className="catalogDetail__priceRow">
                {item.discount_price ? (
                  <>
                    <span className="catalogDetail__priceWas">
                      ${price.toFixed(2)}
                    </span>
                    <span className="catalogDetail__price catalogDetail__price--sale">
                      ${Number(item.discount_price).toFixed(2)}
                    </span>
                  </>
                ) : (
                  <span className="catalogDetail__price">
                    ${price.toFixed(2)}
                  </span>
                )}

                {item.size && (
                  <span className="catalogDetail__meta">{item.size}</span>
                )}
              </div>

              {showColors && (
                <div className="catalogDetail__block">
                  <span className="catalogDetail__label">
                    {item.color ? item.color.name : t("catalogDetail.color")}
                  </span>

                  <div className="catalogDetail__colorOptions">
                    {item.color_options!.map((option) => (
                      <button
                        key={option.slug}
                        type="button"
                        className={`catalogDetail__colorBtn${
                          option.is_current ? " is-active" : ""
                        }`}
                        style={{ background: option.color.hex }}
                        onClick={() => {
                          if (option.is_current) return;
                          navigate(`/catalog/item/${option.slug}`);
                        }}
                        aria-label={option.color.name}
                        aria-current={option.is_current}
                        title={option.color.name}
                      />
                    ))}
                  </div>
                </div>
              )}

              {showSizes && (
                <div className="catalogDetail__block">
                  <span className="catalogDetail__label">
                    {t("catalogDetail.size")}
                  </span>

                  <div className="catalogDetail__pillRow">
                    {sizeOptions.map((option) => (
                      <button
                        key={option.slug}
                        type="button"
                        className={`catalogDetail__sizeBtn${
                          option.isCurrent ? " is-active" : ""
                        }`}
                        onClick={() => {
                          if (option.isCurrent) return;
                          navigate(`/catalog/item/${option.slug}`);
                        }}
                        aria-current={option.isCurrent}
                      >
                        {option.size}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <button
                type="button"
                className="catalogDetail__btn"
                onClick={() => {
                  void onAddToCart();
                }}
                disabled={!variant || adding}
              >
                {adding ? "Adding..." : t("catalogDetail.addToCart")}
              </button>

              <div className="catalogDetail__details">
                {parsed.lead && (
                  <p className="catalogDetail__desc">{parsed.lead}</p>
                )}

                {notes.length > 0 && (
                  <div className="catalogDetail__block">
                    <span className="catalogDetail__label">
                      {t("catalogDetail.scent")}
                    </span>

                    <div className="catalogDetail__tags">
                      {notes.map((note) => (
                        <span key={note} className="catalogDetail__tag">
                          {note}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {rows.length > 0 && (
                  <dl className="catalogDetail__facts">
                    {rows.map((row) => (
                      <React.Fragment key={row.key}>
                        <dt>{row.label}</dt>
                        <dd>{row.values.join(" · ")}</dd>
                      </React.Fragment>
                    ))}
                  </dl>
                )}
              </div>

              {scents.length > 0 && (
                <div className="catalogDetail__related">
                  <span className="catalogDetail__label">
                    {t("catalogDetail.collectionScents")}
                  </span>

                  <div className="catalogDetail__pillRow">
                    {scents.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        className="catalogDetail__scentBtn"
                        onClick={() => navigate(`/catalog/item/${s.slug}`)}
                        aria-label={`${t("catalogDetail.openScent")}: ${s.name}`}
                      >
                        {s.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      {zoomImg && (
        <div
          className="catalogDetail__zoom"
          role="dialog"
          aria-modal="true"
          aria-label={`Large image of ${item.name}`}
        >
          <button
            type="button"
            className="catalogDetail__zoomBackdrop"
            onClick={() => setZoomImg("")}
            aria-label="Close image preview"
          />

          <div className="catalogDetail__zoomContent">
            <button
              type="button"
              className="catalogDetail__zoomClose"
              onClick={() => setZoomImg("")}
              aria-label="Close image preview"
            >
              ×
            </button>

            <img
              src={zoomImg}
              className="catalogDetail__zoomImg"
              alt={item.name}
            />
          </div>
        </div>
      )}
    </main>
  );
};

export default CatalogDetail;