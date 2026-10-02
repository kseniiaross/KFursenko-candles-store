import React from "react";
import "../../styles/CustomerCare/Delivery.css";

const Delivery: React.FC = () => {
  return (
    <main className="cc-page" aria-label="Delivery">
      <section className="cc-hero" aria-label="Delivery information">
        <div className="cc-hero__inner">
          <p className="cc-hero__kicker">Customer care</p>
          <h1 className="cc-hero__title">Delivery</h1>
          <p className="cc-hero__subtitle">
            Every candle is poured by hand once you order it. Here is exactly
            what happens next, and what it costs.
          </p>

          <div className="cc-cards" role="list">
            <article className="cc-card" role="listitem">
              <h2 className="cc-card__title">Shipping cost</h2>
              <p className="cc-card__text">
                Calculated at checkout from your address and the weight of your
                order — usually <strong>$8–14</strong> within the USA. You pick
                the option you want.
              </p>
              <div className="cc-card__note">
                No markup. You pay the carrier rate we pay.
              </div>
            </article>

            <article className="cc-card" role="listitem">
              <h2 className="cc-card__title">Production time</h2>
              <p className="cc-card__text">
                Each order is made to order. Pouring, curing and packing take{" "}
                <strong>3–5 business days</strong> before your parcel ships.
              </p>
              <div className="cc-card__note">
                If we can make it faster — we will.
              </div>
            </article>

            <article className="cc-card" role="listitem">
              <h2 className="cc-card__title">Shipping time</h2>
              <p className="cc-card__text">
                We ship from <strong>Brooklyn, NY</strong> with USPS and UPS.
                Transit runs <strong>2–7 business days</strong> depending on how
                far your order travels.
              </p>
              <div className="cc-card__note">
                Faster services are offered at checkout if you need one.
              </div>
            </article>
          </div>

          <div className="cc-panel">
            <h3 className="cc-panel__title">Quick summary</h3>

            <ul className="cc-list">
              <li className="cc-list__item">
                <span className="cc-badge">$8–14</span>
                <span className="cc-list__text">
                  Shipping, calculated at checkout
                </span>
              </li>
              <li className="cc-list__item">
                <span className="cc-badge">3–5 days</span>
                <span className="cc-list__text">
                  Production — your candle is made after you order
                </span>
              </li>
              <li className="cc-list__item">
                <span className="cc-badge">2–7 days</span>
                <span className="cc-list__text">
                  Transit from Brooklyn, USPS or UPS
                </span>
              </li>
              <li className="cc-list__item">
                <span className="cc-badge">USA</span>
                <span className="cc-list__text">
                  We ship within the United States only
                </span>
              </li>
            </ul>

            <p className="cc-panel__fine">
              Your tracking number appears in your order details as soon as the
              label is printed, and follows the parcel from Brooklyn to your
              door. For a gift note or a specific delivery date, contact us
              before ordering and we will do our best.
            </p>
          </div>

          <div className="cc-panel">
            <h3 className="cc-panel__title">Good to know</h3>

            <p className="cc-panel__fine">
              Candles are heavier than they look — glass makes up most of the
              weight — so shipping is priced by the real weight of your parcel
              rather than a flat fee. Ordering two or three at once costs far
              less per candle than ordering them separately.
            </p>

            <p className="cc-panel__fine">
              In summer we pack with extra insulation where we can, but soy wax
              softens above roughly 80°F. If a heat wave is forecast for your
              area, it is worth waiting a few days.
            </p>

            <p className="cc-panel__fine">
              If a parcel arrives damaged, send us a photo within 7 days of
              delivery and we will replace it.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
};

export default Delivery;