import React from "react";
import { useTranslation } from "react-i18next";
import "../styles/Contacts.css";

const SUPPORT_EMAIL = "k.fursenko.hc@gmail.com";

const Contacts: React.FC = () => {
  const { t } = useTranslation();

  return (
    <main className="contacts" aria-labelledby="contacts-title">
      <div className="contacts__container">
        <header className="contacts__hero">
          <p className="contacts__eyebrow">KFursenko Candles</p>

          <h1 id="contacts-title" className="contacts__title">
            {t("contacts.title")}
          </h1>

          <p className="contacts__subtitle">
            {t("contacts.subtitleLine1")}
            <br />
            {t("contacts.subtitleLine2")}
          </p>
        </header>

        <section
          className="contacts__card"
          aria-labelledby="contacts-support-title"
        >
          <div className="contacts__content">
            <p className="contacts__kicker">{t("contacts.pageLabel")}</p>

            <h2 id="contacts-support-title" className="contacts__cardTitle">
              {t("contacts.supportEmail")}
            </h2>

            <p className="contacts__text">
              We are happy to help with questions about orders, delivery,
              product details, gifting, and custom requests.
            </p>

            <p className="contacts__text">
              We usually reply as quickly as possible during business hours, and
              we do our best to keep communication warm, clear, and helpful.
            </p>

            <p className="contacts__text contacts__text--soft">
              For the fastest support, please include your name and order number
              if your message is about an existing purchase.
            </p>

            <a
              href={`mailto:${SUPPORT_EMAIL}`}
              className="contacts__emailLink"
              aria-label={`${t("contacts.supportEmail")}: ${SUPPORT_EMAIL}`}
            >
              {SUPPORT_EMAIL}
            </a>

            <p className="contacts__note">
              We aim to respond quickly and with care.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
};

export default Contacts;