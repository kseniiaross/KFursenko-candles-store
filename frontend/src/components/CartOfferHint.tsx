import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import api from "../api/axiosInstance";
import { useAppSelector } from "../store/hooks";
import type { CartLine } from "../store/cartSlice";

import "../styles/CartOfferHint.css";

type Promotion = {
  offer_slug: string;
  offer_title: string;
  badge_text: string;
  /** The free candle comes from the offer's own group. */
  reward_group: boolean;
  in_cart: number;
  needed: number;
  free_so_far: number;
};

/**
 * A quiet line in the cart saying how close the basket is to a free candle.
 *
 * The modal fires once and can be dismissed; someone who closed it would
 * otherwise never hear about the offer again. This stays put and costs the
 * shopper nothing to ignore, which is why it says its piece in one sentence
 * and does not ask for a click.
 */
const CartOfferHint: React.FC = () => {
  const cartItems = useAppSelector(
    (state) => (state.cart.items ?? []) as CartLine[]
  );

  const [promotions, setPromotions] = useState<Promotion[]>([]);

  const signature = cartItems
    .map((item) => `${item.variant_id}x${item.quantity}`)
    .sort()
    .join(",");

  useEffect(() => {
    if (!signature) {
      setPromotions([]);
      return;
    }

    let active = true;

    const load = async (): Promise<void> => {
      try {
        const response = await api.post("/orders/offer-progress/", {
          items: cartItems.map((item) => ({
            variant_id: item.variant_id,
            quantity: item.quantity,
          })),
        });

        if (!active) return;

        setPromotions((response.data?.promotions ?? []) as Promotion[]);
      } catch {
        // Silent: the discount applies at checkout whether or not this
        // line rendered.
        if (active) setPromotions([]);
      }
    };

    void load();

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  if (promotions.length === 0) return null;

  return (
    <div className="cartHint" role="status">
      {promotions.map((promotion) => (
        <div key={promotion.offer_slug} className="cartHint__row">
          <span className="cartHint__badge">
            {promotion.badge_text || "Offer"}
          </span>

          <p className="cartHint__text">
            {promotion.free_so_far > 0 ? (
              <>
                <strong>
                  {promotion.free_so_far === 1
                    ? "One candle is already free."
                    : `${promotion.free_so_far} candles are already free.`}
                </strong>{" "}
                Add{" "}
                {promotion.needed === 1
                  ? "one more"
                  : `${promotion.needed} more`}{" "}
                and the next one is on us.
              </>
            ) : (
              <>
                Add{" "}
                <strong>
                  {promotion.needed === 1
                    ? "one more candle"
                    : `${promotion.needed} more candles`}
                </strong>{" "}
                from this offer and{" "}
                {promotion.reward_group
                  ? "one of them is free."
                  : "the cheapest of the three is free."}
              </>
            )}{" "}
            <Link
              to={`/offers/${promotion.offer_slug}`}
              className="cartHint__link"
            >
              See eligible candles
            </Link>
          </p>
        </div>
      ))}
    </div>
  );
};

export default CartOfferHint;