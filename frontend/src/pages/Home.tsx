import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import lightImage from "../assets/images/lightmode.webp";
import darkImage from "../assets/images/darkmode.webp";
import logoImage from "../assets/images/Logo.png";

import { useTheme } from "../theme/ThemeProvider";

import "../styles/Home.css";

type HomeProps = {
  firstName: string | null;
  isLoggedIn: boolean;
};

const Home: React.FC<HomeProps> = () => {
  const { t } = useTranslation();
  const { theme } = useTheme();

  const backgroundImage = useMemo(() => {
    return theme === "light" ? lightImage : darkImage;
  }, [theme]);

  return (
    <main className={`home home--${theme}`} aria-label={t("home.homePage")}>
      <div className="home__media" aria-hidden="true">
        <img
          key={backgroundImage}
          className="home__image"
          src={backgroundImage}
          alt=""
          fetchPriority="high"
          decoding="async"
        />

        <div className="home__overlay" />
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
    </main>
  );
};

export default Home;