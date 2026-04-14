import React from "react";
import { Link } from "react-router-dom";

import "../styles/PaymentCancel.css";

const PaymentCancel: React.FC = () => {
  return (
    <main className="paymentCancel" aria-labelledby="payment-cancel-title">
      <div className="paymentCancel__inner">
        <section
          className="paymentCancel__card"
          aria-describedby="payment-cancel-description"
        >
          <p className="paymentCancel__kicker">Payment</p>

          <h1 id="payment-cancel-title" className="paymentCancel__title">
            Payment canceled
          </h1>

          <p
            id="payment-cancel-description"
            className="paymentCancel__description"
          >
            No worries — your payment was not completed. You can return to checkout
            and try again whenever you are ready.
          </p>

          <div className="paymentCancel__actions">
            <Link
              to="/checkout"
              className="paymentCancel__button paymentCancel__button--primary"
            >
              Back to checkout
            </Link>

            <Link
              to="/cart"
              className="paymentCancel__button paymentCancel__button--secondary"
            >
              Return to cart
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
};

export default PaymentCancel;