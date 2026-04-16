import React from "react";
import { useTranslation } from "react-i18next";
import "../styles/Support.css";

const SUPPORT_EMAIL = "k.fursenko.hc@gmail.com";

/*
 Support page structure follows accessibility and semantic HTML practices.

 - main landmark for screen readers
 - heading hierarchy (h1 -> h2 -> h3)
 - section grouping for FAQ
 - mailto link accessible via keyboard
*/

const Support: React.FC = () => {
  const { t } = useTranslation();

  return (
    <main className="support" aria-labelledby="support-title">
      <div className="support__container">
        <header className="support__hero">
          <p className="support__eyebrow">KFursenko Candles</p>

          <h1 id="support-title" className="support__title">
            {t("support.title")}
          </h1>

          <p className="support__subtitle">
            {t("support.subtitleLine1")}
            <br />
            {t("support.subtitleLine2")}
          </p>
        </header>

        <section
          className="support__faq"
          aria-labelledby="support-faq-title"
        >
          <h2 id="support-faq-title" className="support__sectionTitle">
            {t("support.faq")}
          </h2>

          <div className="support__faqList">

            <article className="support__faqItem">
              <h3 className="support__faqQuestion">
                {t("support.shippingQuestion")}
              </h3>
              <p className="support__faqAnswer">
                {t("support.shippingAnswer")}
              </p>
            </article>

            <article className="support__faqItem">
              <h3 className="support__faqQuestion">
                {t("support.returnQuestion")}
              </h3>
              <p className="support__faqAnswer">
                {t("support.returnAnswer")}
              </p>
            </article>

            <article className="support__faqItem">
              <h3 className="support__faqQuestion">
                {t("support.orderQuestion")}
              </h3>
              <p className="support__faqAnswer">
                {t("support.orderAnswer")}
              </p>
            </article>

          </div>
        </section>

        <section
          className="support__contact"
          aria-labelledby="support-contact-title"
        >
          <h2 id="support-contact-title" className="support__sectionTitle">
            {t("support.contactTitle")}
          </h2>

          <p className="support__contactText">
            {t("support.contactText")}
          </p>

          {/* mailto ensures accessibility for screen readers and keyboard navigation */}
          <a
            href={`mailto:${SUPPORT_EMAIL}`}
            className="support__email"
            aria-label={`Support email ${SUPPORT_EMAIL}`}
          >
            {SUPPORT_EMAIL}
          </a>

          <p className="support__note">
            {t("support.responseTime")}
          </p>
        </section>
      </div>
    </main>
  );
};

export default Support;