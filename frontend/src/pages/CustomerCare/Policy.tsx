import React from "react";
import "../../styles/CustomerCare/Policy.css";

const Policy: React.FC = () => {
  return (
    <main className="cc-page" aria-labelledby="policy-page-title">
      <section className="cc-hero" aria-label="Store policy information">
        <div className="cc-hero__inner">
          <p className="cc-hero__kicker">Customer care</p>

          <h1 id="policy-page-title" className="cc-hero__title">
            Policy
          </h1>

          <p className="cc-hero__subtitle">
            Below is our store policy for cancellations, refunds, returns, and
            damaged items. If you have any questions, please contact us.
          </p>

          <div className="cc-cards" role="list" aria-label="Policy highlights">
            <article className="cc-card" role="listitem">
              <h2 className="cc-card__title">Order cancellation (24 hours)</h2>
              <p className="cc-card__text">
                You may request a cancellation and a full refund within{" "}
                <strong>24 hours</strong> of placing your order, as long as the
                order has <strong>not</strong> entered production or shipped.
              </p>
              <p className="cc-card__note">
                Handmade products may start production quickly, so please
                contact us as soon as possible.
              </p>
            </article>

            <article className="cc-card" role="listitem">
              <h2 className="cc-card__title">Made-to-order items</h2>
              <p className="cc-card__text">
                Our candles are <strong>handmade / made to order</strong>. For
                this reason, we do not accept returns or refunds for{" "}
                <strong>change of mind</strong> once the order is in production
                or has shipped.
              </p>
              <p className="cc-card__note">
                Please review your cart, address, and order details before
                checkout.
              </p>
            </article>

            <article className="cc-card" role="listitem">
              <h2 className="cc-card__title">Damaged or incorrect orders</h2>
              <p className="cc-card__text">
                If your order arrives <strong>damaged</strong> or{" "}
                <strong>incorrect</strong>, please contact us within{" "}
                <strong>48 hours</strong> of delivery. We will help with a
                replacement or a refund, depending on the situation.
              </p>
              <p className="cc-card__note">
                We will ask for photos (item + packaging + shipping label).
              </p>
            </article>
          </div>

          <section className="cc-panel" aria-labelledby="policy-details-title">
            <h2 id="policy-details-title" className="cc-panel__title">
              Details
            </h2>

            <div className="cc-sections">
              <section className="cc-section" aria-labelledby="policy-refunds-title">
                <h3 id="policy-refunds-title" className="cc-section__title">
                  Refunds
                </h3>

                <ul className="cc-list">
                  <li className="cc-list__item">
                    <span className="cc-badge">24 hours</span>
                    <span className="cc-list__text">
                      Full refund is available if the order is cancelled within
                      24 hours and hasn’t entered production or shipping.
                    </span>
                  </li>

                  <li className="cc-list__item">
                    <span className="cc-badge">Damages</span>
                    <span className="cc-list__text">
                      If approved, refunds are issued to the original payment
                      method. Bank processing time may vary.
                    </span>
                  </li>
                </ul>
              </section>

              <section
                className="cc-section"
                aria-labelledby="policy-returns-title"
              >
                <h3 id="policy-returns-title" className="cc-section__title">
                  Returns &amp; exchanges
                </h3>

                <ul className="cc-list">
                  <li className="cc-list__item">
                    <span className="cc-badge">No change of mind</span>
                    <span className="cc-list__text">
                      We don’t accept returns or exchanges for change of mind on
                      made-to-order items.
                    </span>
                  </li>

                  <li className="cc-list__item">
                    <span className="cc-badge">Incorrect item</span>
                    <span className="cc-list__text">
                      If you received the wrong item, contact us within 48 hours
                      and we’ll arrange a replacement or refund.
                    </span>
                  </li>
                </ul>
              </section>

              <section className="cc-section" aria-labelledby="policy-damage-title">
                <h3 id="policy-damage-title" className="cc-section__title">
                  How to report damage
                </h3>

                <div className="cc-callout">
                  <p className="cc-callout__text">
                    To help us resolve the issue quickly, please include:
                  </p>

                  <ul className="cc-bullets">
                    <li>Your order number</li>
                    <li>Clear photos of the damaged item</li>
                    <li>Photos of the box or packaging</li>
                    <li>Photo of the shipping label</li>
                  </ul>

                  <p className="cc-callout__fine">
                    Claims submitted after 48 hours may not be eligible.
                  </p>
                </div>
              </section>

              <section className="cc-section" aria-labelledby="policy-address-title">
                <h3 id="policy-address-title" className="cc-section__title">
                  Address / order changes
                </h3>

                <ul className="cc-list">
                  <li className="cc-list__item">
                    <span className="cc-badge">ASAP</span>
                    <span className="cc-list__text">
                      If you need to change your address or order details,
                      contact us as soon as possible, ideally within 24 hours.
                    </span>
                  </li>
                </ul>
              </section>
            </div>

            <p className="cc-panel__fine">
              We reserve the right to refuse requests that appear fraudulent or
              abusive. This policy may be updated from time to time.
            </p>
          </section>
        </div>
      </section>
    </main>
  );
};

export default Policy;