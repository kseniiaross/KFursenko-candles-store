import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import "../styles/Footer.css";

const INSTAGRAM_URL =
  "https://www.instagram.com/kfursenko_hc?igsh=MTV0ZHA2dmxlbnZ1eA==";
const ETSY_URL = "https://kfursenko.etsy.com";

const LOGIN_CHOICE_PATH = "/login-choice";

function InstagramIcon(): React.ReactElement {
  return (
    <svg className="footer__icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7.5 2h9A5.5 5.5 0 0 1 22 7.5v9A5.5 5.5 0 0 1 16.5 22h-9A5.5 5.5 0 0 1 2 16.5v-9A5.5 5.5 0 0 1 7.5 2Zm0 2A3.5 3.5 0 0 0 4 7.5v9A3.5 3.5 0 0 0 7.5 20h9a3.5 3.5 0 0 0 3.5-3.5v-9A3.5 3.5 0 0 0 16.5 4h-9Z" />
      <path d="M12 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10Zm0 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z" />
      <path d="M17.6 6.4a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z" />
    </svg>
  );
}

function EtsyIcon(): React.ReactElement {
  return (
    <svg className="footer__icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm4.6 13.9c-.3 1.7-1.7 2.9-3.4 2.9H8V6h5.2c1.6 0 3 1.2 3.2 2.8l-1.7.3c-.1-.8-.7-1.3-1.5-1.3H10v3.2h4.5v1.6H10v3.8h3.3c.9 0 1.6-.6 1.7-1.5l1.6.3Z" />
    </svg>
  );
}

const Footer: React.FC = () => {
  const { t } = useTranslation();

  const loginChoiceWithNext = (next: string): string =>
    `${LOGIN_CHOICE_PATH}?next=${encodeURIComponent(next)}`;

  const links = useMemo(
    () => ({
      candles: [
        { label: t("footer.allCandles"), to: "/catalog" },
        { label: t("footer.containerCandles"), to: "/catalog/container" },
        { label: t("footer.moldedCandles"), to: "/catalog/molded" },
        { label: t("footer.collections"), to: "/collections" },
        { label: t("footer.customCandle"), to: "/custom-candle" },
      ],
      care: [
        { label: t("footer.delivery"), to: "/delivery" },
        { label: t("footer.payments"), to: "/payments" },
        { label: t("footer.policy"), to: "/policy" },
        { label: t("footer.support"), to: "/support" },
      ],
      about: [
        { label: t("footer.storyMission"), to: "/story-mission" },
        { label: t("footer.gallery"), to: "/gallery" },
        { label: t("footer.reviews"), to: "/reviews" },
        { label: t("footer.contacts"), to: "/contacts" },
      ],
      quick: [
        { label: t("footer.cart"), to: "/cart" },
        { label: t("footer.orders"), to: loginChoiceWithNext("/orders") },
        { label: t("footer.quiz"), to: "/recommendation-quiz" },
        { label: t("footer.login"), to: loginChoiceWithNext("/login") },
        { label: t("footer.register"), to: loginChoiceWithNext("/register") },
      ],
    }),
    [t]
  );

  const year = new Date().getFullYear();

  return (
    <footer className="footer" aria-label={t("footer.brand")}>
      <div className="footer__overlay" aria-hidden="true" />

      <div className="footer__panel">
        <div className="footer__inner">
          <div className="footer__top">
            <div className="footer__brandBlock">
              <p className="footer__brand">{t("footer.brand")}</p>
              <p className="footer__tagline">{t("footer.tagline")}</p>
            </div>

            <nav className="footer__social" aria-label="Social links">
              <a
                className="footer__socialLink"
                href={INSTAGRAM_URL}
                target="_blank"
                rel="noreferrer"
                aria-label="Instagram"
              >
                <InstagramIcon />
              </a>

              <a
                className="footer__socialLink"
                href={ETSY_URL}
                target="_blank"
                rel="noreferrer"
                aria-label="Etsy"
              >
                <EtsyIcon />
              </a>
            </nav>
          </div>

          <nav className="footer__grid" aria-label="Footer navigation">
            <section className="footer__col" aria-labelledby="footer-candles-title">
              <h2 id="footer-candles-title" className="footer__title">
                {t("footer.candles")}
              </h2>

              {links.candles.map((item) => (
                <Link key={item.label} className="footer__link" to={item.to}>
                  {item.label}
                </Link>
              ))}
            </section>

            <section className="footer__col" aria-labelledby="footer-care-title">
              <h2 id="footer-care-title" className="footer__title">
                {t("footer.customerCare")}
              </h2>

              {links.care.map((item) => (
                <Link key={item.label} className="footer__link" to={item.to}>
                  {item.label}
                </Link>
              ))}
            </section>

            <section className="footer__col" aria-labelledby="footer-about-title">
              <h2 id="footer-about-title" className="footer__title">
                {t("footer.about")}
              </h2>

              {links.about.map((item) => (
                <Link key={item.label} className="footer__link" to={item.to}>
                  {item.label}
                </Link>
              ))}
            </section>

            <section className="footer__col" aria-labelledby="footer-quick-title">
              <h2 id="footer-quick-title" className="footer__title">
                {t("footer.quick")}
              </h2>

              {links.quick.map((item) => (
                <Link key={item.label} className="footer__link" to={item.to}>
                  {item.label}
                </Link>
              ))}
            </section>
          </nav>

          <div className="footer__bottom">
            <span className="footer__copy">
              {t("footer.copyright", { year })}
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;