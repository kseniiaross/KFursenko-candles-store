import React from "react";
import { Link } from "react-router-dom";

import "../../styles/offers/HolidayOffer.css";

const HolidayOffer: React.FC = () => {
  return (
    <main className="holidayOffer" aria-labelledby="holiday-offer-title">
      <div className="holidayOffer__inner">
        <header className="holidayOffer__header">
          <p className="holidayOffer__kicker">Offers</p>

          <h1 id="holiday-offer-title" className="holidayOffer__title">
            Spooky Season Offer
          </h1>

          <p className="holidayOffer__lead">
            10% off our single-wick candles and the Halloween collection.
            Smoke, spice and dark amber — the scents that suit a long October
            evening.
          </p>
        </header>

        <div className="holidayOffer__dates" role="note">
          <span className="holidayOffer__datesLabel">Runs</span>
          <span className="holidayOffer__datesValue">
            1 October – 31 October 2026
          </span>
        </div>

        <section className="holidayOffer__terms" aria-label="Offer terms">
          <h2 className="holidayOffer__termsTitle">The details</h2>

          <ul className="holidayOffer__list">
            <li className="holidayOffer__item">
              The discount is applied automatically at checkout. There is no
              code to enter.
            </li>
            <li className="holidayOffer__item">
              It covers single-wick candles and everything in the Halloween
              collection. Discounted items show the old price struck through
              beside the new one.
            </li>
            <li className="holidayOffer__item">
              The offer ends at 11:59pm on 31 October 2026. Orders placed after
              that are charged the regular price, even if the candle was in the
              basket beforehand.
            </li>
            <li className="holidayOffer__item">
              It does not stack with the 10% welcome discount for new shoppers.
              Whichever gives you the better price is the one you get.
            </li>
            <li className="holidayOffer__item">
              Candles are made to order, so allow 3–5 business days for pouring
              before your parcel ships. Ordering early in the month is the
              safest way to have them lit by Halloween.
            </li>
            <li className="holidayOffer__item">
              Shipping is calculated separately at checkout and is not
              discounted.
            </li>
          </ul>
        </section>

        <div className="holidayOffer__actions">
          <Link
            to="/catalog/collection/halloween"
            className="holidayOffer__btn holidayOffer__btn--primary"
          >
            Shop the Halloween collection
          </Link>

          <Link
            to="/catalog"
            className="holidayOffer__btn holidayOffer__btn--secondary"
          >
            Browse all candles
          </Link>
        </div>
      </div>
    </main>
  );
};

export default HolidayOffer;