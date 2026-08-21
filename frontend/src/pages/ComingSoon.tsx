import React from "react";
import { Link } from "react-router-dom";

import "../styles/ComingSoon.css";

type ComingSoonProps = {
  kicker: string;
  title: string;
  subtitle: string;
};

/**
 * Lightweight placeholder for nav/footer destinations that don't have a
 * real page built yet (collections, offers, reviews). Keeps the link
 * working and tells the visitor what to expect instead of silently
 * bouncing them back to the homepage.
 */
const ComingSoon: React.FC<ComingSoonProps> = ({ kicker, title, subtitle }) => {
  return (
    <main className="cc-page" aria-label={title}>
      <section className="cc-hero" aria-label={title}>
        <div className="cc-hero__inner">
          <p className="cc-hero__kicker">{kicker}</p>
          <h1 className="cc-hero__title">{title}</h1>
          <p className="cc-hero__subtitle">{subtitle}</p>

          <p className="cc-hero__subtitle cc-hero__note">
            This page is on its way. In the meantime, browse the full
            catalog below.
          </p>

          <Link to="/catalog" className="cc-hero__cta">
            Continue shopping
          </Link>
        </div>
      </section>
    </main>
  );
};

export default ComingSoon;
