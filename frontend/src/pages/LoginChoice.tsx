import React, { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import loginImage from "../assets/images/login_choice.webp";

import "../styles/LoginChoice.css";

function isSafePath(path: string | null): path is string {
  return Boolean(path && path.startsWith("/") && !path.startsWith("//"));
}

const LoginChoice: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();

  const nextParam = useMemo(() => {
    const params = new URLSearchParams(location.search);
    const rawNext = params.get("next");
    const safeNext = isSafePath(rawNext) ? rawNext : null;

    return safeNext ? `?next=${encodeURIComponent(safeNext)}` : "";
  }, [location.search]);

  /** Answers the question the visitor is actually weighing here: what do
   *  I get for signing up? An empty page answered nothing. */
  const reasons = [
    {
      key: "discount",
      title: t("loginChoice.perkDiscountTitle"),
      text: t("loginChoice.perkDiscountText"),
    },
    {
      key: "mood",
      title: t("loginChoice.perkMoodTitle"),
      text: t("loginChoice.perkMoodText"),
    },
    {
      key: "checkout",
      title: t("loginChoice.perkCheckoutTitle"),
      text: t("loginChoice.perkCheckoutText"),
    },
  ];

  return (
    <main className="loginChoice" aria-labelledby="login-choice-title">
      <div className="loginChoice__media" aria-hidden="true">
        <img
          src={loginImage}
          alt=""
          className="loginChoice__img"
          decoding="async"
        />
      </div>

      <section
        className="loginChoice__panel"
        aria-describedby="login-choice-subtitle"
      >
        <div className="loginChoice__inner">
          <header className="loginChoice__header">
            <p className="loginChoice__eyebrow">KFursenko Candles</p>

            <h1 id="login-choice-title" className="loginChoice__title">
              {t("loginChoice.title")}
            </h1>

            <p id="login-choice-subtitle" className="loginChoice__subtitle">
              {t("loginChoice.subtitle")}
            </p>
          </header>

          {/* Creating an account is the goal of this page, so it leads. */}
          <nav
            className="loginChoice__buttons"
            aria-label={t("loginChoice.pageLabel")}
          >
            <Link
              to={`/register${nextParam}`}
              className="loginChoice__btn loginChoice__btn--primary"
            >
              {t("loginChoice.register")}
            </Link>

            <Link
              to={`/login${nextParam}`}
              className="loginChoice__btn loginChoice__btn--secondary"
            >
              {t("loginChoice.login")}
            </Link>
          </nav>

          <ul className="loginChoice__perks">
            {reasons.map((reason) => (
              <li key={reason.key} className="loginChoice__perk">
                <span className="loginChoice__perkTitle">{reason.title}</span>
                <span className="loginChoice__perkText">{reason.text}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  );
};

export default LoginChoice;