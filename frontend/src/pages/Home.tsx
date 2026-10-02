import React, { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import summerBanner from "../assets/images/main_banner_summer.webp";
import pumpkinBanner from "../assets/images/banner_pumpkin_blink.webp";
import logoImage from "../assets/images/Logo.png";

import card1 from "../assets/images/card-1.webp";
import card2 from "../assets/images/card-2.webp";
import card3 from "../assets/images/card-3.webp";
import card4 from "../assets/images/card-4.webp";

import "../styles/Home.css";

type HomeProps = {
  firstName: string | null;
  isLoggedIn: boolean;
};

type HomeCard = {
  src: string;
  kicker: string;
  title: string;
  cta: string;
  to: string;
};

/** Scroll distance (in viewport heights) over which the Halloween
 *  banner slides fully over the base banner. */
const SLIDE_DISTANCE = 0.85;

/** Halloween promo — replace with data from the admin Offer model. */
const HALLOWEEN_OFFER = {
  title: "Trick or Treat Yourself",
  text: "Enjoy 5% off the entire collection",
  cta: "Shop the offer",
  to: "/offers/halloween",
};

const Home: React.FC<HomeProps> = () => {
  const { t } = useTranslation();

  const rootRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      el.style.setProperty("--p", "0");
      return;
    }

    let frame = 0;
    let last = -1;

    const update = () => {
      frame = 0;
      const span = window.innerHeight * SLIDE_DISTANCE;
      const progress = span > 0 ? Math.min(window.scrollY / span, 1) : 0;
      const eased = 1 - Math.pow(1 - progress, 3);
      const rounded = Math.round(eased * 1000) / 1000;
      if (rounded !== last) {
        last = rounded;
        el.style.setProperty("--p", String(rounded));
      }
    };

    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  const cards = useMemo<HomeCard[]>(
    () => [
      {
        src: card1,
        kicker: "Sculpted in wax",
        title: "Molded Candles",
        cta: "Shop molded candles",
        to: "/catalog/category/molded-candles",
      },
      {
        src: card2,
        kicker: "Limited offer",
        title: "Buy 2, Get 3",
        cta: "See the offer",
        to: "/offers/buy-2-get-3",
      },
      {
        src: card3,
        kicker: "Made for you",
        title: "Custom Candles",
        cta: "Start your design",
        to: "/custom-candles",
      },
      {
        src: card4,
        kicker: "Seasonal",
        title: "Spring–Summer Collection",
        cta: "Explore the collection",
        to: "/catalog/category/spring-summer-collection",
      },
    ],
    []
  );

  return (
    <main className="home" aria-label={t("home.homePage")} ref={rootRef}>
      <div className="home__media" aria-hidden="true">
        <img
          className="home__image home__image--base"
          src={summerBanner}
          alt=""
          width={1376}
          height={768}
          fetchPriority="high"
          decoding="async"
          sizes="100vw"
        />
        <img
          className="home__image home__image--overlayImage"
          src={pumpkinBanner}
          alt=""
          width={1376}
          height={768}
          loading="lazy"
          decoding="async"
          sizes="100vw"
        />

        <div className="home__overlay" />
      </div>

      {/* Rides with the Halloween banner — kept outside .home__media
          so the link stays reachable for screen readers. */}
      <div className="home__promoLayer">
        <div className="home__promo">
          <h2 className="home__promoTitle">{HALLOWEEN_OFFER.title}</h2>
          <p className="home__promoText">{HALLOWEEN_OFFER.text}</p>
          <Link to={HALLOWEEN_OFFER.to} className="home__promoCta">
            {HALLOWEEN_OFFER.cta}
          </Link>
        </div>
      </div>

      <section className="home__content" aria-label={t("home.brandSection")}>
        <div className="home__logoWrapper">
          <Link
            to="/story-mission"
            className="home__logoLink"
            aria-label={t("home.goToStoryMission")}
          >
            <img
              className="home__logo"
              src={logoImage}
              alt="KFursenko Candles logo"
              decoding="async"
            />
          </Link>
        </div>
      </section>

      {/* Keeps the Halloween banner on screen before the cards arrive */}
      <div className="home__hold" aria-hidden="true" />

      <section className="home__cards" aria-label="Featured collections">
        {cards.map((card) => (
          <Link key={card.to} to={card.to} className="home__card">
            <div className="home__cardMedia">
              <img
                className="home__cardImage"
                src={card.src}
                alt=""
                width={928}
                height={1160}
                loading="lazy"
                decoding="async"
              />
            </div>

            <div className="home__cardBody">
              <p className="home__cardKicker">{card.kicker}</p>
              <h3 className="home__cardTitle">{card.title}</h3>
              <span className="home__cardCta">
                {card.cta}
                <span className="home__cardArrow" aria-hidden="true">
                  →
                </span>
              </span>
            </div>
          </Link>
        ))}
      </section>
    </main>
  );
};

export default Home;