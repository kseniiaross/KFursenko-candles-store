import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import api from "../api/axiosInstance";
import { addToCart as addToCartApi } from "../api/cart";
import { useAppDispatch, useAppSelector } from "../store/hooks";
import { addToCart, setCart } from "../store/cartSlice";
import type { CartLine } from "../store/cartSlice";

import "../styles/OfferModal.css";

type Suggestion = {
  candle_id: number;
  variant_id: number;
  name: string;
  slug: string;
  size: string;
  price: string;
  image: string;
};

type Promotion = {
  offer_slug: string;
  offer_title: string;
  badge_text: string;
  in_cart: number;
  needed: number;
  free_so_far: number;
  suggestions: Suggestion[];
};

/** Long enough for the cart to settle after a burst of clicks, short
 *  enough that the prompt still feels like a reaction. */
const CHECK_DELAY_MS = 900;

/** Pages where a prompt to add more would be an obstruction. */
const MUTED_PATHS = ["/checkout", "/payment", "/login", "/register"];

const OfferModal: React.FC = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();

  const isLoggedIn = useAppSelector((state) => Boolean(state.auth?.isLoggedIn));
  const cartItems = useAppSelector(
    (state) => (state.cart.items ?? []) as CartLine[]
  );

  /** Quantity already in the basket, by variant. The server lists those
   *  variants first; picking one adds to the same line. */
  const heldByVariant = useMemo(
    () =>
      new Map(
        cartItems.map((item) => [Number(item.variant_id), Number(item.quantity) || 0])
      ),
    [cartItems]
  );

  const [promotion, setPromotion] = useState<Promotion | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [adding, setAdding] = useState<number | null>(null);

  const titleId = useId();

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  /** Cart shapes already prompted about. Without this the modal reopens
   *  every time the cart re-renders, which is on every page change. */
  const seenRef = useRef<Set<string>>(new Set());

  const isMuted = MUTED_PATHS.some((path) =>
    location.pathname.startsWith(path)
  );

  const signature = cartItems
    .map((item) => `${item.variant_id}x${item.quantity}`)
    .sort()
    .join(",");

  useEffect(() => {
    if (isMuted || isOpen || !signature) return;
    if (seenRef.current.has(signature)) return;

    let active = true;

    const timer = window.setTimeout(async () => {
      try {
        const response = await api.post("/orders/offer-progress/", {
          items: cartItems.map((item) => ({
            variant_id: item.variant_id,
            quantity: item.quantity,
          })),
        });

        if (!active) return;

        const promotions = (response.data?.promotions ?? []) as Promotion[];

        // Only nudge when a single candle completes the trio. Two away is
        // a shopping decision, not a nudge — and being told twice on the
        // way there is nagging.
        const ready = promotions.find(
          (item) => item.needed === 1 && item.suggestions.length > 0
        );

        seenRef.current.add(signature);

        if (ready) {
          setPromotion(ready);
          setIsOpen(true);
        }
      } catch {
        // A failed prompt is not worth surfacing. The discount still
        // applies at checkout whether or not this modal appeared.
        if (active) seenRef.current.add(signature);
      }
    }, CHECK_DELAY_MS);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, isMuted, isOpen]);

  const close = useCallback(() => {
    setIsOpen(false);
    setPromotion(null);
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    closeRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        close();
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) return;

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          "button:not([disabled]), a[href]"
        )
      );

      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [close, isOpen]);

  const onPick = async (suggestion: Suggestion): Promise<void> => {
    if (adding !== null) return;

    setAdding(suggestion.variant_id);

    dispatch(
      addToCart({
        item: {
          variant_id: suggestion.variant_id,
          candle_id: suggestion.candle_id,
          name: suggestion.name,
          price: Number(suggestion.price) || 0,
          image: suggestion.image || undefined,
          size: suggestion.size,
          quantity: 1,
          isGift: false,
        },
        persistAsGuest: !isLoggedIn,
      })
    );

    try {
      if (isLoggedIn) {
        const serverItems = await addToCartApi({
          variant_id: suggestion.variant_id,
          quantity: 1,
          is_gift: false,
        });

        if (Array.isArray(serverItems) && serverItems.length > 0) {
          dispatch(setCart(serverItems));
        }
      }
    } catch {
      // The line is already in Redux; a sync failure should not undo the
      // shopper's click.
    } finally {
      setAdding(null);
      close();
    }
  };

  if (!isOpen || !promotion) return null;

  return (
    <div className="offerModal" role="presentation">
      <button
        type="button"
        className="offerModal__backdrop"
        onClick={close}
        aria-label="Close"
      />

      <div
        ref={dialogRef}
        className="offerModal__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <button
          ref={closeRef}
          type="button"
          className="offerModal__close"
          onClick={close}
          aria-label="Close"
        >
          ×
        </button>

        <header className="offerModal__header">
          <p className="offerModal__kicker">
            {promotion.badge_text || promotion.offer_title}
          </p>

          <h2 id={titleId} className="offerModal__title">
            One more and the third is free
          </h2>

          <p className="offerModal__lead">
            You have {promotion.in_cart} candles from this offer in your
            basket. Add one more and the cheapest of the three costs nothing —
            the discount is applied at checkout.
          </p>
        </header>

        <ul className="offerModal__grid" role="list">
          {promotion.suggestions.map((suggestion) => {
            const held = heldByVariant.get(suggestion.variant_id) ?? 0;

            return (
              <li key={suggestion.variant_id} className="offerCard">
                <button
                  type="button"
                  className="offerCard__btn"
                  onClick={() => void onPick(suggestion)}
                  disabled={adding !== null}
                >
                  <span className="offerCard__media">
                    {suggestion.image ? (
                      <img
                        src={suggestion.image}
                        alt=""
                        className="offerCard__img"
                        loading="lazy"
                        decoding="async"
                      />
                    ) : (
                      <span className="offerCard__img offerCard__img--empty" />
                    )}
                  </span>

                  <span className="offerCard__name">{suggestion.name}</span>

                  <span className="offerCard__meta">
                    {suggestion.size} · ${Number(suggestion.price).toFixed(2)}
                  </span>

                  {held > 0 && (
                    <span className="offerCard__held">In your basket ×{held}</span>
                  )}

                  <span className="offerCard__action">
                    {adding === suggestion.variant_id
                      ? "Adding…"
                      : held > 0
                        ? "Add another"
                        : "Add"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        <footer className="offerModal__footer">
          <button
            type="button"
            className="offerModal__browse"
            onClick={() => {
              close();
              navigate(`/offers/${promotion.offer_slug}`);
            }}
          >
            See all candles in this offer
          </button>

          <button type="button" className="offerModal__skip" onClick={close}>
            No thanks
          </button>
        </footer>

        <p className="offerModal__note">
          The free candle is the lowest-priced of the three. This offer does
          not combine with other discounts.
        </p>
      </div>
    </div>
  );
};

export default OfferModal;