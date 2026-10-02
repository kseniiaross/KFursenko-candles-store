import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAppSelector } from "../store/hooks";
import modalImage from "../assets/images/discount_modal.webp";

import "../styles/DiscountModal.css";

const STORAGE_KEY = "kf_welcome_offer_v1";

/** Long enough that a dismissal sticks, short enough that the offer is
 *  still reachable for someone who comes back next season. */
const SNOOZE_MS = 30 * 24 * 60 * 60 * 1000;

/** A beat after the page settles — an instant modal reads as a popup ad
 *  and gets closed before it is read. */
const OPEN_DELAY_MS = 1200;

/** Pages where the offer would be in the way rather than useful. */
const MUTED_PATHS = [
  "/register",
  "/login",
  "/login-choice",
  "/checkout",
  "/cart",
  "/payment",
];

type ModalMemory = {
  dismissedAt?: number;
  /** Set once the visitor has an account — the offer is theirs already. */
  done?: boolean;
};

function readMemory(): ModalMemory {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ModalMemory) : {};
  } catch {
    return {};
  }
}

function writeMemory(value: ModalMemory): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Private browsing can block writes. The modal showing again is a
    // smaller problem than throwing here.
  }
}

const DiscountModal: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  const isLoggedIn = useAppSelector((state) => Boolean(state.auth?.isLoggedIn));

  const [isOpen, setIsOpen] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState("");

  const titleId = useId();
  const termsId = useId();
  const errorId = useId();

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  const isMuted = MUTED_PATHS.some((path) =>
    location.pathname.startsWith(path)
  );

  useEffect(() => {
    if (isLoggedIn) {
      writeMemory({ done: true });
      setIsOpen(false);
      return;
    }

    if (isMuted) return;

    const memory = readMemory();

    if (memory.done) return;
    if (memory.dismissedAt && Date.now() - memory.dismissedAt < SNOOZE_MS) {
      return;
    }

    const timer = window.setTimeout(() => setIsOpen(true), OPEN_DELAY_MS);

    return () => window.clearTimeout(timer);
  }, [isLoggedIn, isMuted]);

  const dismiss = useCallback(() => {
    writeMemory({ dismissedAt: Date.now() });
    setIsOpen(false);
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    closeRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        dismiss();
        return;
      }

      if (event.key !== "Tab" || !dialogRef.current) return;

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], input:not([disabled])'
        )
      );

      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [dismiss, isOpen]);

  if (!isOpen) return null;

  const onClaim = (): void => {
    if (!accepted) {
      setError(t("discountModal.termsRequired"));
      return;
    }

    writeMemory({ dismissedAt: Date.now() });
    setIsOpen(false);
    navigate("/register");
  };

  return (
    <div className="discountModal" role="presentation">
      <button
        type="button"
        className="discountModal__backdrop"
        onClick={dismiss}
        aria-label={t("common.close")}
      />

      <div
        ref={dialogRef}
        className="discountModal__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <button
          ref={closeRef}
          type="button"
          className="discountModal__close"
          onClick={dismiss}
          aria-label={t("common.close")}
        >
          ×
        </button>

        <div className="discountModal__media" aria-hidden="true">
          <img
            src={modalImage}
            alt=""
            className="discountModal__img"
            decoding="async"
          />
        </div>

        <div className="discountModal__panel">
          <p className="discountModal__brand">KFursenko Candles</p>

          <p className="discountModal__lead">{t("discountModal.lead")}</p>

          <p id={titleId} className="discountModal__amount">
            {t("discountModal.amount")}
          </p>

          <p className="discountModal__sub">{t("discountModal.sub")}</p>

          <label className="discountModal__terms" htmlFor={termsId}>
            <input
              id={termsId}
              type="checkbox"
              className="discountModal__checkbox"
              checked={accepted}
              onChange={(event) => {
                setAccepted(event.target.checked);
                setError("");
              }}
              aria-describedby={error ? errorId : undefined}
            />

            <span className="discountModal__termsText">
              {t("discountModal.terms")}
            </span>
          </label>

          {error ? (
            <p id={errorId} className="discountModal__error" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="button"
            className="discountModal__cta"
            onClick={onClaim}
          >
            {t("discountModal.cta")}
            <span className="discountModal__ctaNote">
              {t("discountModal.ctaNote")}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default DiscountModal;