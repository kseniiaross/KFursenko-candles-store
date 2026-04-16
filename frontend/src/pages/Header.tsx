import React, {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import "../styles/Header.css";
import logo from "../assets/images/Logo.png";
import { clearAuthStorage } from "../utils/token";
import { useTheme } from "../theme/ThemeProvider";
import { useAppSelector } from "../store/hooks";

type HeaderProps = {
  firstName: string | null;
  isLoggedIn: boolean;
  onLogout: () => void;
};

const LOGIN_CHOICE_PATH = "/login-choice";

type CartLikeItem = {
  quantity?: number;
};

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "ru", label: "Русский" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
];

const Header: React.FC<HeaderProps> = ({ firstName, isLoggedIn, onLogout }) => {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { theme, toggleTheme } = useTheme();

  const cartCount = useAppSelector((state) => {
    const cartState = state.cart as
      | { items?: CartLikeItem[]; totalQuantity?: number; count?: number }
      | undefined;

    if (!cartState) return 0;
    if (typeof cartState.totalQuantity === "number") return cartState.totalQuantity;
    if (typeof cartState.count === "number") return cartState.count;
    if (!Array.isArray(cartState.items)) return 0;
    return cartState.items.reduce((sum, item) => sum + (item.quantity ?? 0), 0);
  });

  const menuButtonId = useId();
  const menuDialogId = useId();
  const menuTitleId = useId();
  const accountButtonId = useId();
  const accountMobileButtonId = useId();
  const accountMenuId = useId();
  const accountMobileMenuId = useId();
  const languageButtonId = useId();
  const languageMenuId = useId();

  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isAccountOpen, setIsAccountOpen] = useState(false);
  const [isLanguageOpen, setIsLanguageOpen] = useState(false);

  // Separate refs for desktop and mobile account dropdowns
  const accountDesktopRef = useRef<HTMLDivElement | null>(null);
  const accountMobileRef = useRef<HTMLDivElement | null>(null);

  const languageRef = useRef<HTMLDivElement | null>(null);
  const menuDialogRef = useRef<HTMLDivElement | null>(null);
  const menuCloseButtonRef = useRef<HTMLButtonElement | null>(null);
  const menuTriggerButtonRef = useRef<HTMLButtonElement | null>(null);

  const loginChoiceWithNext = useCallback((next: string): string => {
    return `${LOGIN_CHOICE_PATH}?next=${encodeURIComponent(next)}`;
  }, []);

  const accountLabel = useMemo(() => {
    if (!isLoggedIn) return t("common.goToMyAccount");
    const normalizedFirstName = firstName?.trim();
    return normalizedFirstName || t("common.goToMyAccount");
  }, [firstName, isLoggedIn, t]);

  const currentModeLabel = useMemo(
    () => (theme === "light" ? "Light" : "Dark"),
    [theme]
  );

  const themeAriaLabel = useMemo(
    () =>
      theme === "light"
        ? "Current mode: light. Activate to switch to dark mode."
        : "Current mode: dark. Activate to switch to light mode.",
    [theme]
  );

  const links = useMemo(
    () => ({
      candles: [
        { label: t("header.allCandles"), to: "/catalog" },
        { label: t("header.containerCandles"), to: "/catalog/container" },
        { label: t("header.moldedCandles"), to: "/catalog/molded" },
        { label: t("header.springSummer"), to: "/collections/spring-summer" },
        { label: t("header.autumnWinter"), to: "/collections/autumn-winter" },
        { label: t("header.customCandle"), to: "/custom-candle" },
        { label: t("header.singleWick"), to: "/catalog/single-wick" },
        { label: t("header.multipleWick"), to: "/catalog/multiple-wick" },
        { label: t("header.candleHolders"), to: "/candle-holders" },
      ],
      offers: [
        { label: t("header.allOffers"), to: "/offers" },
        { label: t("header.newShopper"), to: "/offers/new-shopper" },
        { label: t("header.buyOneGetTwo"), to: "/offers/buy-1-get-2" },
        { label: t("header.holidayOffers"), to: "/offers/holidays" },
      ],
      orders: [
        {
          label: t("common.orders"),
          to: isLoggedIn ? "/orders" : loginChoiceWithNext("/orders"),
        },
        { label: t("header.delivery"), to: "/delivery" },
        { label: t("header.payments"), to: "/payments" },
        { label: t("header.policy"), to: "/policy" },
      ],
      about: [
        { label: t("header.storyMission"), to: "/story-mission" },
        { label: t("header.contacts"), to: "/contacts" },
      ],
    }),
    [isLoggedIn, loginChoiceWithNext, t]
  );

  const openMenu = useCallback(() => setIsMenuOpen(true), []);
  const closeMenu = useCallback(() => setIsMenuOpen(false), []);
  const toggleAccount = useCallback(() => setIsAccountOpen((prev) => !prev), []);
  const closeAccount = useCallback(() => setIsAccountOpen(false), []);
  const toggleLanguage = useCallback(() => setIsLanguageOpen((prev) => !prev), []);
  const closeLanguage = useCallback(() => setIsLanguageOpen(false), []);

  const handleLogout = useCallback(() => {
    clearAuthStorage();
    closeAccount();
    onLogout();
    navigate("/", { replace: true });
  }, [closeAccount, navigate, onLogout]);

  const handleLanguageSelect = useCallback(
    (code: string) => {
      void i18n.changeLanguage(code);
      closeLanguage();
    },
    [i18n, closeLanguage]
  );

  const handleMenuNavigation = useCallback(() => closeMenu(), [closeMenu]);

  // Close account dropdown when clicking outside — checks BOTH desktop and mobile refs
  useEffect(() => {
    if (!isAccountOpen) return;
    const handleClickOutside = (event: PointerEvent) => {
      const target = event.target as Node;
      const inDesktop = accountDesktopRef.current?.contains(target);
      const inMobile = accountMobileRef.current?.contains(target);
      if (!inDesktop && !inMobile) {
        closeAccount();
      }
    };
    document.addEventListener("pointerdown", handleClickOutside);
    return () => document.removeEventListener("pointerdown", handleClickOutside);
  }, [closeAccount, isAccountOpen]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (languageRef.current && !languageRef.current.contains(event.target as Node)) {
        closeLanguage();
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [closeLanguage]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (isAccountOpen) closeAccount();
      if (isLanguageOpen) closeLanguage();
      if (isMenuOpen) {
        closeMenu();
        menuTriggerButtonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [closeAccount, closeLanguage, closeMenu, isAccountOpen, isLanguageOpen, isMenuOpen]);

  useEffect(() => {
    if (!isMenuOpen) return;
    menuCloseButtonRef.current?.focus();

    const handleFocusTrap = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !menuDialogRef.current) return;

      const focusableElements = menuDialogRef.current.querySelectorAll<
        HTMLButtonElement | HTMLAnchorElement | HTMLSelectElement | HTMLInputElement
      >(
        'button:not([disabled]), a[href], select:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );

      const focusable = Array.from(focusableElements);
      if (focusable.length === 0) return;
      const firstFocusable = focusable[0];
      const lastFocusable = focusable[focusable.length - 1];
      const activeElement = document.activeElement;
      if (event.shiftKey && activeElement === firstFocusable) {
        event.preventDefault();
        lastFocusable.focus();
      } else if (!event.shiftKey && activeElement === lastFocusable) {
        event.preventDefault();
        firstFocusable.focus();
      }
    };
    document.addEventListener("keydown", handleFocusTrap);
    return () => document.removeEventListener("keydown", handleFocusTrap);
  }, [isMenuOpen]);

  // ─── Account dropdown JSX — reused in desktop and mobile with different refs ───
  const renderAccountDropdown = (
    ref: React.RefObject<HTMLDivElement | null>,
    buttonId: string,
    menuId: string
  ) => {
    if (!isLoggedIn) {
      return (
        <Link
          to="/login-choice"
          className="header__navTextButton header__navTextButton--link"
        >
          {t("common.goToMyAccount")}
        </Link>
      );
    }

    return (
      <div className="header__account" ref={ref}>
        <button
          id={buttonId}
          type="button"
          className="header__navTextButton"
          onClick={toggleAccount}
          aria-expanded={isAccountOpen}
          aria-controls={menuId}
          aria-haspopup="menu"
        >
          {accountLabel}
        </button>

        {isAccountOpen && (
          <div
            id={menuId}
            className="header__dropdown"
            role="menu"
            aria-labelledby={buttonId}
          >
            <Link
              to="/profile"
              className="header__dropdownItem"
              role="menuitem"
              onClick={closeAccount}
            >
              {t("common.profile")}
            </Link>
            <Link
              to="/orders"
              className="header__dropdownItem"
              role="menuitem"
              onClick={closeAccount}
            >
              {t("common.orders")}
            </Link>
            <button
              type="button"
              className="header__dropdownItem header__dropdownItem--button"
              role="menuitem"
              onClick={handleLogout}
            >
              {t("common.logout")}
            </button>
          </div>
        )}
      </div>
    );
  };

  // ─── Nav row — menu button + account ───
  const renderNavRow = (
    ref: React.RefObject<HTMLDivElement | null>,
    buttonId: string,
    menuId: string
  ) => (
    <>
      <button
        id={menuButtonId}
        ref={menuTriggerButtonRef}
        type="button"
        className="header__navTextButton"
        onClick={openMenu}
        aria-expanded={isMenuOpen}
        aria-controls={menuDialogId}
        aria-haspopup="dialog"
      >
        {t("common.menu")}
      </button>

      {renderAccountDropdown(ref, buttonId, menuId)}
    </>
  );

  // ─── Controls row — theme + language + cart ───
  const controlsRow = (
    <>
      <button
        type="button"
        className="header__themeToggle"
        onClick={toggleTheme}
        aria-label={themeAriaLabel}
        aria-pressed={theme === "dark"}
        title={themeAriaLabel}
      >
        <span className="header__themeDot" aria-hidden="true" />
        <span className="header__chipText">{currentModeLabel}</span>
      </button>

      <div className="header__languageBox" ref={languageRef}>
        <button
          id={languageButtonId}
          type="button"
          className="header__navTextButton header__langButton"
          onClick={toggleLanguage}
          aria-expanded={isLanguageOpen}
          aria-controls={languageMenuId}
          aria-haspopup="menu"
          aria-label={`Language selector. Current language: ${i18n.language}`}
        >
          {t("common.language")}
        </button>

        {isLanguageOpen && (
          <div
            id={languageMenuId}
            className="header__dropdown header__dropdown--language"
            role="menu"
            aria-labelledby={languageButtonId}
          >
            {LANGUAGES.map((lang) => (
              <button
                key={lang.code}
                type="button"
                className={`header__dropdownItem header__dropdownItem--button${
                  i18n.language === lang.code ? " header__dropdownItem--active" : ""
                }`}
                role="menuitemradio"
                aria-checked={i18n.language === lang.code}
                onClick={() => handleLanguageSelect(lang.code)}
              >
                {lang.label}
                {i18n.language === lang.code && (
                  <span className="header__langCheck" aria-hidden="true">✓</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      <Link
        to="/cart"
        className="header__cartLink"
        aria-label={`Shopping cart${cartCount > 0 ? `, ${cartCount} items` : ", empty"}`}
      >
        <span className="header__chipText">{t("catalog.shoppingCart")}</span>
        {cartCount > 0 && (
          <span className="header__cartCount" aria-hidden="true">
            {cartCount > 99 ? "99+" : cartCount}
          </span>
        )}
      </Link>
    </>
  );

  return (
    <>
      <header className="header" aria-label="Site header">
        <div className="header__inner">

          {/* ── DESKTOP LAYOUT ──
              Left: logo + nav buttons
              Right: theme + language + cart
          */}
          <div className="header__left header__desktopLeft">
            <Link to="/" className="header__logoLink" aria-label="Go to home page">
              <img className="header__logoImg" src={logo} alt="KFursenko Candles" />
            </Link>
            {renderNavRow(accountDesktopRef, accountButtonId, accountMenuId)}
          </div>

          <div className="header__right header__desktopRight">
            {controlsRow}
          </div>

          {/* ── MOBILE LAYOUT ──
              Logo on left spanning full height.
              Two rows on the right:
                Row 1: Menu | Account
                Row 2: Light | Language | Cart
          */}
          <div className="header__mobileLogo">
            <Link to="/" className="header__logoLink" aria-label="Go to home page">
              <img className="header__logoImg" src={logo} alt="KFursenko Candles" />
            </Link>
          </div>

          <div className="header__mobileRows">
            <div className="header__mobileRow1">
              {renderNavRow(accountMobileRef, accountMobileButtonId, accountMobileMenuId)}
            </div>
            <div className="header__mobileRow2">
              {controlsRow}
            </div>
          </div>

        </div>
      </header>

      {isMenuOpen && (
        <div
          id={menuDialogId}
          className="menu"
          role="dialog"
          aria-modal="true"
          aria-labelledby={menuTitleId}
        >
          <button
            type="button"
            className="menu__overlay"
            onClick={closeMenu}
            aria-label={t("common.close")}
          />

          <div ref={menuDialogRef} className="menu__content">
            <button
              ref={menuCloseButtonRef}
              type="button"
              className="menu__close"
              onClick={closeMenu}
              aria-label={t("common.close")}
            >
              ×
            </button>

            <div className="menu__top">
              <h2 id={menuTitleId} className="menu__title">
                {t("header.menuTitle")}
              </h2>
            </div>

            <nav className="menu__grid" aria-label={t("header.menuTitle")}>
              <div className="menu__column">
                <h3 className="menu__department">{t("header.candles")}</h3>
                {links.candles.map((linkItem) => (
                  <Link key={linkItem.label} to={linkItem.to} className="menu__link" onClick={handleMenuNavigation}>
                    {linkItem.label}
                  </Link>
                ))}
              </div>
              <div className="menu__column">
                <h3 className="menu__department">{t("header.offers")}</h3>
                {links.offers.map((linkItem) => (
                  <Link key={linkItem.label} to={linkItem.to} className="menu__link" onClick={handleMenuNavigation}>
                    {linkItem.label}
                  </Link>
                ))}
              </div>
              <div className="menu__column">
                <h3 className="menu__department">{t("header.orders")}</h3>
                {links.orders.map((linkItem) => (
                  <Link key={linkItem.label} to={linkItem.to} className="menu__link" onClick={handleMenuNavigation}>
                    {linkItem.label}
                  </Link>
                ))}
              </div>
              <div className="menu__column">
                <h3 className="menu__department">{t("header.about")}</h3>
                {links.about.map((linkItem) => (
                  <Link key={linkItem.label} to={linkItem.to} className="menu__link" onClick={handleMenuNavigation}>
                    {linkItem.label}
                  </Link>
                ))}
              </div>
            </nav>
          </div>
        </div>
      )}
    </>
  );
};

export default Header;