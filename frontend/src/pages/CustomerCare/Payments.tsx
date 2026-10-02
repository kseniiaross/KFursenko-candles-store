import React from "react";
import "../../styles/CustomerCare/Payments.css";

const Payments: React.FC = () => {

  return (
    <main
      className="cc-page"
      aria-label="Payments"
    >
      <section className="cc-hero" aria-label="Payment information">
        <div className="cc-hero__inner">
          <p className="cc-hero__kicker">Customer care</p>
          <h1 className="cc-hero__title">Payments</h1>
          <p className="cc-hero__subtitle">
            We keep payments secure and simple. Card details are handled by Stripe.
          </p>

          <div className="cc-cards" role="list">
            <article className="cc-card" role="listitem">
              <h2 className="cc-card__title">Secure checkout</h2>
              <p className="cc-card__text">
                All payments are processed through <strong>Stripe</strong> — a trusted
                payment platform used by millions of businesses.
              </p>
              <div className="cc-card__note">
                We do not handle your card number directly.
              </div>
            </article>

            <article className="cc-card" role="listitem">
              <h2 className="cc-card__title">We don’t store card data</h2>
              <p className="cc-card__text">
                We <strong>do not store</strong> your full card number, CVV, or magnetic
                stripe data. Sensitive payment information is collected and processed
                by Stripe.
              </p>
              <div className="cc-card__note">
                This helps keep your data protected and reduces risk.
              </div>
            </article>

            <article className="cc-card" role="listitem">
              <h2 className="cc-card__title">Receipts & confirmations</h2>
              <p className="cc-card__text">
                After checkout you’ll receive an order confirmation and payment
                receipt (email or on-screen), depending on your checkout flow.
              </p>
              <div className="cc-card__note">
                Keep the confirmation for your records.
              </div>
            </article>
          </div>

          <div className="cc-panel">
            <h3 className="cc-panel__title">Important notes</h3>

            <ul className="cc-list">
              <li className="cc-list__item">
                <span className="cc-badge">Stripe</span>
                <span className="cc-list__text">
                  Payments are processed by Stripe. We receive only limited payment
                  metadata (e.g., status, amount, and last 4 digits when available).
                </span>
              </li>

              <li className="cc-list__item">
                <span className="cc-badge">Security</span>
                <span className="cc-list__text">
                  Stripe uses industry-standard security measures and encryption for
                  payment processing.
                </span>
              </li>

              <li className="cc-list__item">
                <span className="cc-badge">Currency</span>
                <span className="cc-list__text">
                  Prices are shown and charged in <strong>USD</strong> unless stated
                  otherwise. Your bank may apply additional fees.
                </span>
              </li>

              <li className="cc-list__item">
                <span className="cc-badge">Refunds</span>
                <span className="cc-list__text">
                  Refunds (if approved) are returned to the original payment method
                  via Stripe. Processing times depend on your bank.
                </span>
              </li>
            </ul>

            <p className="cc-panel__fine">
              This page is provided for informational purposes and does not replace
              our official policies. For details, please review the Policy page.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
};

export default Payments;