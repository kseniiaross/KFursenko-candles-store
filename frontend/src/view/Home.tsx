import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import lightVideo from "../assets/images/lightmode.mp4";
import darkVideo from "../assets/images/darkmode.mp4";
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

  const videoRef = useRef<HTMLVideoElement | null>(null);

  const [isVideoVisible, setIsVideoVisible] = useState(false);
  const [videoReady, setVideoReady] = useState(false);

  const prefersReducedMotion = useMemo(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }, []);

  const videoSource = useMemo(() => {
    return theme === "light" ? lightVideo : darkVideo;
  }, [theme]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    setVideoReady(false);
    setIsVideoVisible(false);

    const handleCanPlay = async (): Promise<void> => {
      setVideoReady(true);

      if (prefersReducedMotion) return;

      try {
        video.currentTime = 0;
        await video.play();
        requestAnimationFrame(() => {
          setIsVideoVisible(true);
        });
      } catch {
        setIsVideoVisible(true);
      }
    };

    const handleEnded = (): void => {
      video.currentTime = 0;
      void video.play().catch(() => {});
    };

    video.pause();
    video.src = videoSource;
    video.load();

    if (video.readyState >= 3) {
      void handleCanPlay();
    } else {
      video.addEventListener("canplay", handleCanPlay, { once: true });
    }

    video.addEventListener("ended", handleEnded);

    return () => {
      video.removeEventListener("ended", handleEnded);
      video.removeEventListener("canplay", handleCanPlay);
    };
  }, [videoSource, prefersReducedMotion]);

  return (
    <main className={`home home--${theme}`} aria-label={t("home.homePage")}>
      <div className="home__media" aria-hidden="true">
        <video
          ref={videoRef}
          key={videoSource}
          className={`home__video ${videoReady && isVideoVisible ? "is-visible" : ""}`}
          autoPlay={!prefersReducedMotion}
          muted
          loop
          playsInline
          preload="auto"
          src={videoSource}
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
            />
          </Link>
        </div>
      </section>
    </main>
  );
};

export default Home;