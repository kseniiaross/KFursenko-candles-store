import React from "react";
import { Link } from "react-router-dom";

import { useAppSelector } from "../../store/hooks";

import "../../styles/offers/NewShoppers.css";

const NewShoppers: React.FC = () => {
  const isLoggedIn = useAppSelector((state) => Boolean(state.auth?.isLoggedIn));

  return (
    <main className="newShoppers" aria-labelledby="new-shoppers-title">
      <div className="newShoppers__inner">
        <header className="newShoppers__header">
          <p className="newShoppers__kicker">Offers</p>

          <h1 id="new-shoppers-title" className="newShoppers__title">
            10% off your first order
          </h1>

          <p className="newShoppers__lead">
            Create an account and your first order comes with 10% off. Nothing
            to remember, nothing to type in — the price simply drops when you
            reach checkout.
          </p>
        </header>

        <div className="newShoppers__highlight" role="note">
          <span className="newShoppers__highlightLabel">How to get it</span>
          <span className="newShoppers__highlightValue">
            Sign up, add candles, checkout — the discount is already there
          </span>
        </div>

        <section
          className="newShoppers__terms"
          aria-labelledby="new-shoppers-terms"
        >
          <h2 id="new-shoppers-terms" className="newShoppers__sectionTitle">
            The details
          </h2>

          <ul className="newShoppers__list">
            <li className="newShoppers__item">
              The discount applies to your first order and is worked out at
              checkout. You will see it on the order summary before you pay.
            </li>
            <li className="newShoppers__item">
              It is tied to your account, so you need to be signed in for it to
              apply. Ordering as a guest means paying full price.
            </li>
            <li className="newShoppers__item">
              The offer stays available for a while after you sign up rather
              than expiring the same day — take your time choosing a scent.
            </li>
            <li className="newShoppers__item">
              It does not stack with seasonal promotions. If a candle is already
              discounted, whichever offer gives you the better price is the one
              that applies.
            </li>
            <li className="newShoppers__item">
              Shipping is calculated separately at checkout from your address
              and the weight of the parcel. It is not discounted.
            </li>
            <li className="newShoppers__item">
              One welcome discount per person. Additional accounts do not
              qualify for a second one.
            </li>
          </ul>
        </section>

        <div className="newShoppers__actions">
          {isLoggedIn ? (
            <>
              <Link
                to="/catalog"
                className="newShoppers__btn newShoppers__btn--primary"
              >
                Start shopping
              </Link>

              <Link
                to="/recommendation-quiz"
                className="newShoppers__btn newShoppers__btn--secondary"
              >
                Take the scent quiz
              </Link>
            </>
          ) : (
            <>
              <Link
                to="/register"
                className="newShoppers__btn newShoppers__btn--primary"
              >
                Create an account
              </Link>

              <Link
                to="/login"
                className="newShoppers__btn newShoppers__btn--secondary"
              >
                I already have one
              </Link>
            </>
          )}
        </div>

        {!isLoggedIn && (
          <p className="newShoppers__footnote">
            Already ordered from us before? The welcome discount is for first
            orders, but the seasonal offers are open to everyone —{" "}
            <Link to="/offers" className="newShoppers__inlineLink">
              see what is running now
            </Link>
            .
          </p>
        )}
      </div>
    </main>
  );
};

export default NewShoppers;