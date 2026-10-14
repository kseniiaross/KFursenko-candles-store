import React from "react";

import { useAppDispatch, useAppSelector } from "../store/hooks";
import { dismissCartNotices } from "../store/cartSlice";

import "../styles/CartNotices.css";

/** What signing in changed in the cart: a candle that sold out, was
 *  switched off, or was lowered to what's left. Shown on the cart and at
 *  checkout until dismissed, so the shopper isn't surprised by the total. */
const CartNotices: React.FC = () => {
  const dispatch = useAppDispatch();
  const notices = useAppSelector((state) => state.cart.notices);

  if (notices.length === 0) return null;

  return (
    <div className="cartNotices" role="status">
      <ul className="cartNotices__list">
        {notices.map((notice) => (
          <li key={notice} className="cartNotices__item">
            {notice}
          </li>
        ))}
      </ul>

      <button
        type="button"
        className="cartNotices__dismiss"
        onClick={() => dispatch(dismissCartNotices())}
      >
        OK
      </button>
    </div>
  );
};

export default CartNotices;
