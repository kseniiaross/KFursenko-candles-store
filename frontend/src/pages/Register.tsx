import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { isAxiosError } from "axios";
import { useTranslation } from "react-i18next";

import { useAppDispatch } from "../store/hooks";
import { setCredentials } from "../store/authSlice";
import { notifyAuthChanged } from "../utils/token";

import { getTerms, registerThenLoginWithProfile, type Terms } from "../api/auth";

import registerImage from "../assets/images/register.webp";

import "../styles/Register.css";

type RegisterFormState = {
  first_name: string;
  last_name: string;
  phone_number: string;
  email: string;
  password: string;
};

function isSafePath(path: string | null): path is string {
  return Boolean(path && path.startsWith("/") && !path.startsWith("//"));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** The server's answer when the terms the page sent aren't the current
 *  ones, or none were sent: the current terms, to show and ask again. */
function readTermsConflict(
  error: unknown
): { code: string; terms: Terms } | null {
  if (!isAxiosError(error) || error.response?.status !== 409) return null;

  const data = error.response.data;
  if (!isRecord(data) || !isRecord(data.terms)) return null;

  const { version, locale, text } = data.terms;
  if (
    typeof version !== "string" ||
    typeof locale !== "string" ||
    typeof text !== "string"
  ) {
    return null;
  }

  return { code: String(data.code ?? ""), terms: { version, locale, text } };
}

const Register: React.FC = () => {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();

  const [form, setForm] = useState<RegisterFormState>({
    first_name: "",
    last_name: "",
    phone_number: "",
    email: "",
    password: "",
  });

  const [fieldError, setFieldError] = useState<Partial<Record<keyof RegisterFormState, string>>>({});

  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // The sign-up discount's terms, as the server renders them now. Every new
  // account accepts them (accounts/views.py). null while loading, if the
  // request failed, or when no discount runs; the server then answers the
  // submit with the terms to show, so the shopper is never stuck.
  const [terms, setTerms] = useState<Terms | null>(null);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [termsMessage, setTermsMessage] = useState<string | null>(null);
  const termsRef = useRef<HTMLInputElement | null>(null);
  // Bumped when the server asks for the terms again. The box is disabled
  // until the submit settles, so it is focused after, not in the catch.
  const [askAgain, setAskAgain] = useState(0);

  useEffect(() => {
    if (askAgain && !submitting) termsRef.current?.focus();
  }, [askAgain, submitting]);

  const shownVersion = useRef<string | undefined>(undefined);
  shownVersion.current = terms?.version;

  useEffect(() => {
    let active = true;

    getTerms(locale)
      .then((current) => {
        if (!active) return;
        // Other words than the ones ticked, after a change of language: ask again.
        if (current?.version !== shownVersion.current) setTermsAccepted(false);
        setTerms(current);
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, [locale]);

  const nextParam = useMemo(() => {
    const params = new URLSearchParams(location.search);
    const rawNext = params.get("next");
    return isSafePath(rawNext) ? rawNext : null;
  }, [location.search]);

  const safeNextQuery = nextParam ? `?next=${encodeURIComponent(nextParam)}` : "";

  const firstNameErrorId = "register-first-name-error";
  const lastNameErrorId = "register-last-name-error";
  const phoneErrorId = "register-phone-error";
  const emailErrorId = "register-email-error";
  const passwordErrorId = "register-password-error";
  const serverErrorId = "register-server-error";
  const termsTextId = "register-terms-text";
  const termsMessageId = "register-terms-message";

  const getRegisterErrorMessage = (error: unknown): string => {
    if (!isAxiosError(error)) {
      return t("register.errors.network");
    }

    const status = error.response?.status;
    const data = error.response?.data;

    if (isRecord(data)) {
      const detail = data.detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail.trim();
      }

      const keys = [
        "email",
        "password",
        "phone_number",
        "first_name",
        "last_name",
        "non_field_errors",
      ] as const;

      for (const key of keys) {
        const value = data[key];

        if (
          Array.isArray(value) &&
          value.length > 0 &&
          typeof value[0] === "string"
        ) {
          return value[0];
        }

        if (typeof value === "string" && value.trim()) {
          return value.trim();
        }
      }
    }

    if (status === 400) {
      return t("register.errors.invalidForm");
    }

    return t("register.errors.failed");
  };

  const validate = (): boolean => {
    const errors: Partial<Record<keyof RegisterFormState, string>> = {};

    if (!form.first_name.trim()) {
      errors.first_name = t("register.errors.firstNameRequired");
    }

    if (!form.last_name.trim()) {
      errors.last_name = t("register.errors.lastNameRequired");
    }

    const phone = form.phone_number.trim();
    if (!phone) {
      errors.phone_number = t("register.errors.phoneRequired");
    } else if (!/^\+?[0-9\s().-]{7,20}$/.test(phone)) {
      errors.phone_number = t("register.errors.phoneInvalid");
    }

    const email = form.email.trim();
    if (!email) {
      errors.email = t("register.errors.emailRequired");
    } else if (!email.includes("@")) {
      errors.email = t("register.errors.emailInvalid");
    }

    if (!form.password) {
      errors.password = t("register.errors.passwordRequired");
    } else if (form.password.length < 8) {
      errors.password = t("register.errors.passwordMin");
    }

    setFieldError(errors);

    const termsOk = !terms || termsAccepted;
    setTermsMessage(termsOk ? null : t("register.termsRequired"));

    return Object.keys(errors).length === 0 && termsOk;
  };

  const handleFieldChange =
    (key: keyof RegisterFormState) =>
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      const value = event.target.value;

      setForm((prev) => ({
        ...prev,
        [key]: value,
      }));

      // Clear field-level and form-level errors as the user corrects input.
      setFieldError((prev) => ({
        ...prev,
        [key]: undefined,
      }));
      setServerError(null);
    };

  const onSubmit: React.FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    setServerError(null);

    if (!validate()) {
      return;
    }

    setSubmitting(true);

    try {
      const { user, tokens } = await registerThenLoginWithProfile({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone_number: form.phone_number.trim(),
        email: form.email.trim(),
        password: form.password,
        terms_version: terms && termsAccepted ? terms.version : undefined,
        locale,
      });

      const access = String(tokens.access || "").trim();
      const refresh = tokens.refresh ? String(tokens.refresh).trim() : "";

      if (!access) {
        setServerError(t("register.errors.loginAfterRegisterFailed"));
        navigate(`/login${safeNextQuery}`, { replace: true });
        return;
      }

      dispatch(
        setCredentials({
          access,
          refresh: refresh || undefined,
          user,
        })
      );

      notifyAuthChanged();
      navigate(nextParam ?? "/", { replace: true });
    } catch (error: unknown) {
      const conflict = readTermsConflict(error);

      if (conflict) {
        setTerms(conflict.terms);
        setTermsAccepted(false);
        setTermsMessage(
          conflict.code === "terms_outdated"
            ? t("register.termsChanged")
            : t("register.termsRequired")
        );
        setAskAgain((count) => count + 1);
        return;
      }

      setServerError(getRegisterErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="register" aria-labelledby="register-title">
      <div className="register__media" aria-hidden="true">
        <img
          src={registerImage}
          alt=""
          className="register__img"
          decoding="async"
        />
      </div>

      <section className="register__panel" aria-label={t("register.pageLabel")}>
        <div className="register__inner">
          <header className="register__header">
            <p className="register__eyebrow">KFursenko Candles</p>

            <h1 id="register-title" className="register__title">
              {t("register.title")}
            </h1>

            <p className="register__subtitle">{t("register.subtitle")}</p>
          </header>

          {/* The discount is worked out server-side at checkout, so this is
              a statement of fact rather than a code the visitor must keep. */}
          <p className="register__perk">{t("register.welcomePerk")}</p>

          <form className="register__form" onSubmit={onSubmit} noValidate>
            <div className="register__grid">
              <div className="register__field">
                <label className="register__label" htmlFor="reg_first_name">
                  {t("register.firstName")}
                </label>

                <input
                  id="reg_first_name"
                  className="register__input"
                  type="text"
                  autoComplete="given-name"
                  value={form.first_name}
                  onChange={handleFieldChange("first_name")}
                  disabled={submitting}
                  aria-invalid={Boolean(fieldError.first_name)}
                  aria-describedby={
                    fieldError.first_name ? firstNameErrorId : undefined
                  }
                />

                {fieldError.first_name ? (
                  <p
                    id={firstNameErrorId}
                    className="register__message register__message--error"
                    role="alert"
                  >
                    {fieldError.first_name}
                  </p>
                ) : null}
              </div>

              <div className="register__field">
                <label className="register__label" htmlFor="reg_last_name">
                  {t("register.lastName")}
                </label>

                <input
                  id="reg_last_name"
                  className="register__input"
                  type="text"
                  autoComplete="family-name"
                  value={form.last_name}
                  onChange={handleFieldChange("last_name")}
                  disabled={submitting}
                  aria-invalid={Boolean(fieldError.last_name)}
                  aria-describedby={
                    fieldError.last_name ? lastNameErrorId : undefined
                  }
                />

                {fieldError.last_name ? (
                  <p
                    id={lastNameErrorId}
                    className="register__message register__message--error"
                    role="alert"
                  >
                    {fieldError.last_name}
                  </p>
                ) : null}
              </div>

              <div className="register__field register__field--full register__field--pair">
                <label className="register__label" htmlFor="reg_phone">
                  {t("register.phone")}
                </label>

                <input
                  id="reg_phone"
                  className="register__input"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  value={form.phone_number}
                  onChange={handleFieldChange("phone_number")}
                  disabled={submitting}
                  aria-invalid={Boolean(fieldError.phone_number)}
                  aria-describedby={
                    fieldError.phone_number ? phoneErrorId : undefined
                  }
                />

                {fieldError.phone_number ? (
                  <p
                    id={phoneErrorId}
                    className="register__message register__message--error"
                    role="alert"
                  >
                    {fieldError.phone_number}
                  </p>
                ) : null}
              </div>

              <div className="register__field register__field--full register__field--pair">
                <label className="register__label" htmlFor="reg_email">
                  {t("register.email")}
                </label>

                <input
                  id="reg_email"
                  className="register__input"
                  type="email"
                  autoComplete="email"
                  value={form.email}
                  onChange={handleFieldChange("email")}
                  disabled={submitting}
                  aria-invalid={Boolean(fieldError.email)}
                  aria-describedby={fieldError.email ? emailErrorId : undefined}
                />

                {fieldError.email ? (
                  <p
                    id={emailErrorId}
                    className="register__message register__message--error"
                    role="alert"
                  >
                    {fieldError.email}
                  </p>
                ) : null}
              </div>

              <div className="register__field register__field--full">
                <label className="register__label" htmlFor="reg_password">
                  {t("register.password")}
                </label>

                <input
                  id="reg_password"
                  className="register__input"
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={handleFieldChange("password")}
                  disabled={submitting}
                  aria-invalid={Boolean(fieldError.password)}
                  aria-describedby={
                    fieldError.password ? passwordErrorId : undefined
                  }
                />

                {fieldError.password ? (
                  <p
                    id={passwordErrorId}
                    className="register__message register__message--error"
                    role="alert"
                  >
                    {fieldError.password}
                  </p>
                ) : null}
              </div>
            </div>

            {terms ? (
              <div className="register__terms">
                <div className="register__termsRow">
                  <input
                    ref={termsRef}
                    id="reg_terms"
                    type="checkbox"
                    className="register__termsCheckbox"
                    checked={termsAccepted}
                    onChange={(event) => {
                      setTermsAccepted(event.target.checked);
                      setTermsMessage(null);
                    }}
                    disabled={submitting}
                    aria-invalid={Boolean(termsMessage)}
                    aria-describedby={
                      termsMessage
                        ? `${termsTextId} ${termsMessageId}`
                        : termsTextId
                    }
                  />

                  <label className="register__termsLabel" htmlFor="reg_terms">
                    {t("register.termsConsent")}
                  </label>
                </div>

                <p id={termsTextId} className="register__termsText">
                  {terms.text}
                </p>

                {termsMessage ? (
                  <p
                    id={termsMessageId}
                    className="register__message register__message--error"
                    role="alert"
                  >
                    {termsMessage}
                  </p>
                ) : null}
              </div>
            ) : null}

            <button
              type="submit"
              className="register__cta"
              disabled={submitting}
            >
              {submitting ? t("register.creating") : t("register.register")}
            </button>

            {serverError ? (
              <div
                id={serverErrorId}
                className="register__message register__message--server"
                role="alert"
                aria-live="polite"
              >
                {serverError}
              </div>
            ) : null}
          </form>

          {/* Logging in is a different intent, not a second submit button —
              keeping it out of the form makes that clear. */}
          <p className="register__switch">
            {t("register.haveAccount")}{" "}
            <Link
              to={`/login${safeNextQuery}`}
              className="register__switchLink"
            >
              {t("register.logIn")}
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
};

export default Register;