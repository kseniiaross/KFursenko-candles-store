import React from "react";
import { Link } from "react-router-dom";

import "../styles/Promo.css";

const CONTACT_EMAIL = "k.fursenko.hc@gmail.com";

const STEPS: Array<{ title: string; text: string }> = [
  {
    title: "Tell us the occasion",
    text: "A wedding, a birthday, a housewarming, a corporate gift — the occasion shapes everything else.",
  },
  {
    title: "Choose a scent and a look",
    text: "Pick from our existing scents or describe the one you imagine. Add a name, a date or a short message to the label.",
  },
  {
    title: "Approve the design",
    text: "We send you a label mock-up and a quote. Nothing is poured until you say yes.",
  },
  {
    title: "Hand-poured for you",
    text: "Production takes 5–7 working days after approval, plus shipping.",
  },
];

const CustomCandles: React.FC = () => {
  const subject = encodeURIComponent("Custom candle enquiry");
  const body = encodeURIComponent(
    [
      "Hello K. Fursenko Candles,",
      "",
      "Occasion:",
      "Quantity:",
      "Scent(s) I like:",
      "Text for the label:",
      "Needed by (date):",
      "",
      "Thank you!",
    ].join("\n")
  );

  return (
    <main className="promo" aria-labelledby="custom-title">
      <div className="promo__inner promo__inner--narrow">
        <header className="promo__header">
          <p className="promo__kicker">Made for you</p>
          <h1 id="custom-title" className="promo__title">
            Custom Candles
          </h1>
          <p className="promo__subtitle">
            A candle nobody else will have — your scent, your label, your words.
          </p>
        </header>

        <section className="promo__lead" aria-label="Introduction">
          <p>
            Whether it is a name and a date for a wedding table, a message for
            someone you love, or a bespoke scent for your brand, we pour each
            custom candle by hand in small batches.
          </p>
          <p>
            There is no order form — we would rather hear it in your own words.
            Write to us and tell us what you have in mind.
          </p>
        </section>

        <section className="promo__cta" aria-label="Contact us">
          <p className="promo__ctaLabel">Send your idea to</p>

          <a
            className="promo__email"
            href={`mailto:${CONTACT_EMAIL}?subject=${subject}&body=${body}`}
          >
            {CONTACT_EMAIL}
          </a>

          <p className="promo__ctaNote">
            Include the occasion, how many candles you need and your ideal
            date. We reply within two working days with options and a price.
          </p>
        </section>

        <section className="promo__terms" aria-labelledby="custom-steps-title">
          <h2 id="custom-steps-title" className="promo__termsTitle">
            How it works
          </h2>

          <ol className="promo__steps">
            {STEPS.map((step, index) => (
              <li key={step.title} className="promo__step">
                <span className="promo__stepNum" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3 className="promo__stepTitle">{step.title}</h3>
                  <p className="promo__stepText">{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="promo__terms" aria-labelledby="custom-notes-title">
          <h2 id="custom-notes-title" className="promo__termsTitle">
            Good to know
          </h2>

          <table className="promo__table">
            <caption className="promo__tableCaption">
              Custom order conditions
            </caption>
            <tbody>
              <tr>
                <th scope="row">Lead time</th>
                <td>5–7 working days from approval, plus delivery.</td>
              </tr>
              <tr>
                <th scope="row">Minimum order</th>
                <td>One candle. Discounts start from ten pieces.</td>
              </tr>
              <tr>
                <th scope="row">Label text</th>
                <td>Up to 40 characters keeps the label balanced and legible.</td>
              </tr>
              <tr>
                <th scope="row">Returns</th>
                <td>
                  Personalised candles cannot be returned or exchanged unless
                  they arrive damaged.
                </td>
              </tr>
              <tr>
                <th scope="row">Promotions</th>
                <td>Custom orders are not eligible for site-wide offers.</td>
              </tr>
            </tbody>
          </table>
        </section>

        <p className="promo__back">
          <Link to="/catalog">Browse ready-made candles →</Link>
        </p>
      </div>
    </main>
  );
};

export default CustomCandles;