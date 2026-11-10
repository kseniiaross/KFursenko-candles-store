import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import "../styles/PaymentCancel.css";

const PaymentCancel: React.FC = () => {
  const { t } = useTranslation();

  return (
    <main className="paymentCancel" aria-labelledby="payment-cancel-title">
      <div className="paymentCancel__inner">
        <section
          className="paymentCancel__card"
          aria-describedby="payment-cancel-description"
        >
          <p className="paymentCancel__kicker">{t("checkout.payment")}</p>

          <h1 id="payment-cancel-title" className="paymentCancel__title">
            {t("paymentCancel.title")}
          </h1>

          <p
            id="payment-cancel-description"
            className="paymentCancel__description"
          >
            {t("paymentCancel.subtitle")}
          </p>

          <div className="paymentCancel__actions">
            <Link
              to="/checkout"
              className="paymentCancel__button paymentCancel__button--primary"
            >
              {t("paymentCancel.backToCheckout")}
            </Link>

            <Link
              to="/cart"
              className="paymentCancel__button paymentCancel__button--secondary"
            >
              {t("paymentCancel.returnToCart")}
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
};

export default PaymentCancel;