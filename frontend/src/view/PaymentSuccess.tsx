import React from "react";
import { Link } from "react-router-dom";

import "../styles/PaymentSuccess.css";

const PaymentSuccess: React.FC = () => {
  return (
    <main className="paymentSuccess" aria-labelledby="payment-success-title">
      <div className="paymentSuccess__inner">
        <section
          className="paymentSuccess__card"
          aria-describedby="payment-success-description"
        >
          <p className="paymentSuccess__kicker">Payment</p>

          <h1 id="payment-success-title" className="paymentSuccess__title">
            Payment successful
          </h1>

          <p
            id="payment-success-description"
            className="paymentSuccess__description"
          >
            Thank you. Your order has been confirmed successfully. You can
            continue shopping or view your orders for the latest status.
          </p>

          <div className="paymentSuccess__actions">
            <Link
              to="/orders"
              className="paymentSuccess__button paymentSuccess__button--primary"
            >
              View orders
            </Link>

            <Link
              to="/catalog"
              className="paymentSuccess__button paymentSuccess__button--secondary"
            >
              Back to catalog
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
};

export default PaymentSuccess;