import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import api from "../api/axiosInstance";
import "../styles/Profile.css";

type ProfileFormState = {
  firstName: string;
  lastName: string;
  email: string;
  addressLine1: string;
  apartment: string;
  city: string;
  state: string;
  postalCode: string;
  country: string;
};

type ProfileResponse = {
  first_name: string;
  last_name: string;
  email: string;
  address_line1?: string;
  apartment?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  country?: string;
};

type NominatimResult = {
  display_name: string;
  address: {
    house_number?: string;
    road?: string;
    city?: string;
    town?: string;
    village?: string;
    state?: string;
    postcode?: string;
    country?: string;
    country_code?: string;
  };
};

const API_PROFILE_URL = "/accounts/profile/";
const API_DELETE_ACCOUNT_URL = "/accounts/delete-account/";

export const PROFILE_STORAGE_KEY = "profile_shipping_data";

function safeString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function isValidEmail(value: string): boolean {
  return /\S+@\S+\.\S+/.test(value);
}

function saveProfileToStorage(form: ProfileFormState): void {
  try {
    sessionStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(form));
  } catch {
    // ignore
  }
}

// ─── Nominatim address autocomplete hook ───
function useAddressSuggestions(query: string, enabled: boolean) {
  const [suggestions, setSuggestions] = useState<NominatimResult[]>([]);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);

    const trimmed = query.trim();

    if (!enabled || trimmed.length < 3) {
      setSuggestions([]);
      setLoading(false);
      return;
    }

    setLoading(true);

    timerRef.current = setTimeout(async () => {
      // Cancel previous request
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();

      try {
        // No countrycodes filter — works globally
        // featuretype=street gives street-level results
        const url =
          `https://nominatim.openstreetmap.org/search` +
          `?q=${encodeURIComponent(trimmed)}` +
          `&format=json` +
          `&addressdetails=1` +
          `&limit=6` +
          `&featuretype=street`;

        const response = await fetch(url, {
          signal: abortRef.current.signal,
          headers: {
            "Accept-Language": "en-US,en",
            // Nominatim requires a descriptive User-Agent
            "User-Agent": "KFursenkoCandles/1.0 (kfcandle.com)",
          },
        });

        if (!response.ok) throw new Error("Nominatim error");

        const data = (await response.json()) as NominatimResult[];
        setSuggestions(data.slice(0, 6));
      } catch (err) {
        // Ignore abort errors — they're expected when user keeps typing
        if (err instanceof Error && err.name === "AbortError") return;
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    }, 350);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [query, enabled]);

  return {
    suggestions,
    loading,
    clear: () => {
      setSuggestions([]);
      setLoading(false);
    },
  };
}

const Profile: React.FC = () => {
  const navigate = useNavigate();

  const titleId = useId();
  const subtitleId = useId();
  const modalTitleId = useId();
  const modalTextId = useId();
  const suggestionsId = useId();

  const [form, setForm] = useState<ProfileFormState>({
    firstName: "",
    lastName: "",
    email: "",
    addressLine1: "",
    apartment: "",
    city: "",
    state: "",
    postalCode: "",
    country: "",
  });

  const [addressQuery, setAddressQuery] = useState("");
  const [addressFocused, setAddressFocused] = useState(false);
  const addressFieldRef = useRef<HTMLDivElement | null>(null);

  // Only search when field is focused and user is typing
  const { suggestions, loading: suggestionsLoading, clear: clearSuggestions } =
    useAddressSuggestions(addressQuery, addressFocused);

  const showSuggestions =
    addressFocused && (suggestionsLoading || suggestions.length > 0);

  const [loadingProfile, setLoadingProfile] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [saveErr, setSaveErr] = useState("");

  const [fieldErrors, setFieldErrors] = useState<
    Partial<Record<keyof ProfileFormState, string>>
  >({});

  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const modalRef = useRef<HTMLDivElement | null>(null);
  const deleteCancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const openDeleteButtonRef = useRef<HTMLButtonElement | null>(null);

  // ── Load profile on mount ──
  useEffect(() => {
    let cancelled = false;

    async function fetchProfile(): Promise<void> {
      try {
        setLoadingProfile(true);
        const { data } = await api.get<ProfileResponse>(API_PROFILE_URL);
        if (cancelled) return;

        const loaded: ProfileFormState = {
          firstName: safeString(data.first_name),
          lastName: safeString(data.last_name),
          email: safeString(data.email),
          addressLine1: safeString(data.address_line1),
          apartment: safeString(data.apartment),
          city: safeString(data.city),
          state: safeString(data.state),
          postalCode: safeString(data.postal_code),
          country: safeString(data.country),
        };

        setForm(loaded);
        setAddressQuery(safeString(data.address_line1));
        saveProfileToStorage(loaded);
      } catch {
        if (!cancelled) setSaveErr("We could not load your profile right now.");
      } finally {
        if (!cancelled) setLoadingProfile(false);
      }
    }

    void fetchProfile();
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Close suggestions when clicking outside ──
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        addressFieldRef.current &&
        !addressFieldRef.current.contains(e.target as Node)
      ) {
        setAddressFocused(false);
        clearSuggestions();
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [clearSuggestions]);

  // ── Delete modal keyboard handling ──
  useEffect(() => {
    if (!isDeleteOpen) return;
    deleteCancelButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setIsDeleteOpen(false);

      if (event.key === "Tab" && modalRef.current) {
        const focusable = modalRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
        );
        const arr = Array.from(focusable);
        if (!arr.length) return;
        const first = arr[0];
        const last = arr[arr.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isDeleteOpen]);

  useEffect(() => {
    if (isDeleteOpen) return;
    openDeleteButtonRef.current?.focus();
  }, [isDeleteOpen]);

  // ── Pick a suggestion from Nominatim ──
  const handleSuggestionSelect = useCallback(
    (result: NominatimResult) => {
      const addr = result.address;
      const streetNumber = addr.house_number ?? "";
      const street = addr.road ?? "";
      const streetFull = [streetNumber, street].filter(Boolean).join(" ");
      const city = addr.city ?? addr.town ?? addr.village ?? "";
      const countryCode = (addr.country_code ?? "").toUpperCase();

      setForm((prev) => ({
        ...prev,
        addressLine1: streetFull || prev.addressLine1,
        city: city || prev.city,
        state: addr.state ?? prev.state,
        postalCode: addr.postcode ?? prev.postalCode,
        country: countryCode || prev.country,
      }));
      setAddressQuery(streetFull || result.display_name);
      setAddressFocused(false);
      clearSuggestions();
    },
    [clearSuggestions]
  );

  const onFieldChange =
    (name: keyof ProfileFormState) =>
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      const value = event.target.value;
      setForm((prev) => ({ ...prev, [name]: value }));
      setSaveMsg("");
      setSaveErr("");
      setDeleteError("");
      setFieldErrors((prev) => {
        if (!prev[name]) return prev;
        const next = { ...prev };
        delete next[name];
        return next;
      });
    };

  const onAddressChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setAddressQuery(value);
    setForm((prev) => ({ ...prev, addressLine1: value }));
    setSaveMsg("");
    setSaveErr("");
  };

  const validate = (): boolean => {
    const errors: Partial<Record<keyof ProfileFormState, string>> = {};
    if (!form.firstName.trim()) errors.firstName = "First name is required.";
    if (!form.lastName.trim()) errors.lastName = "Last name is required.";
    if (!form.email.trim()) {
      errors.email = "Email is required.";
    } else if (!isValidEmail(form.email.trim())) {
      errors.email = "Enter a valid email address.";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSave = async (
    event: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    event.preventDefault();
    setSaveMsg("");
    setSaveErr("");
    if (!validate()) return;
    setSaving(true);

    try {
      await api.put(API_PROFILE_URL, {
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        email: form.email.trim(),
        address_line1: form.addressLine1.trim(),
        apartment: form.apartment.trim(),
        city: form.city.trim(),
        state: form.state.trim(),
        postal_code: form.postalCode.trim(),
        country: form.country.trim(),
      });

      saveProfileToStorage(form);
      window.dispatchEvent(new Event("auth-changed"));
      setSaveMsg("Profile updated successfully.");
      setFieldErrors({});
    } catch {
      setSaveErr("Failed to update profile. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAccount = async (): Promise<void> => {
    if (deleting) return;
    setDeleteError("");
    setDeleting(true);

    try {
      await api.post(API_DELETE_ACCOUNT_URL, { confirm: true });
      localStorage.clear();
      sessionStorage.removeItem(PROFILE_STORAGE_KEY);
      navigate("/", { replace: true });
    } catch {
      setDeleteError(
        "We could not delete the account right now. Please try again."
      );
      setDeleting(false);
    }
  };

  const hasStatusMessage = useMemo(
    () => Boolean(saveMsg || saveErr),
    [saveMsg, saveErr]
  );

  return (
    <main
      className="profile"
      aria-labelledby={titleId}
      aria-describedby={subtitleId}
    >
      <div className="profile__shell">
        <header className="profile__head">
          <p className="profile__eyebrow" aria-hidden="true">
            Account
          </p>
          <h1 id={titleId} className="profile__title">
            Profile
          </h1>
          <p id={subtitleId} className="profile__subtitle">
            Manage your account details and shipping information.
          </p>
        </header>

        <section className="profile__card" aria-label="Profile details">
          {loadingProfile ? (
            <div
              className="profile__statusBlock"
              role="status"
              aria-live="polite"
              aria-label="Loading profile"
            >
              Loading profile…
            </div>
          ) : (
            <form
              className="profile__form"
              onSubmit={handleSave}
              noValidate
              aria-label="Edit profile"
            >
              {/* ── Account section ── */}
              <section
                className="profile__section"
                aria-labelledby="profile-account-section"
              >
                <h2
                  id="profile-account-section"
                  className="profile__sectionTitle"
                >
                  Account
                </h2>

                <div className="profile__grid">
                  <div className="profile__field">
                    <label
                      className="profile__label"
                      htmlFor="profile-first-name"
                    >
                      First name
                    </label>
                    <input
                      id="profile-first-name"
                      className="profile__input"
                      type="text"
                      value={form.firstName}
                      onChange={onFieldChange("firstName")}
                      autoComplete="given-name"
                      aria-required="true"
                      aria-invalid={fieldErrors.firstName ? "true" : "false"}
                      aria-describedby={
                        fieldErrors.firstName
                          ? "profile-first-name-error"
                          : undefined
                      }
                    />
                    {fieldErrors.firstName && (
                      <p
                        id="profile-first-name-error"
                        className="profile__fieldError"
                        role="alert"
                      >
                        {fieldErrors.firstName}
                      </p>
                    )}
                  </div>

                  <div className="profile__field">
                    <label
                      className="profile__label"
                      htmlFor="profile-last-name"
                    >
                      Last name
                    </label>
                    <input
                      id="profile-last-name"
                      className="profile__input"
                      type="text"
                      value={form.lastName}
                      onChange={onFieldChange("lastName")}
                      autoComplete="family-name"
                      aria-required="true"
                      aria-invalid={fieldErrors.lastName ? "true" : "false"}
                      aria-describedby={
                        fieldErrors.lastName
                          ? "profile-last-name-error"
                          : undefined
                      }
                    />
                    {fieldErrors.lastName && (
                      <p
                        id="profile-last-name-error"
                        className="profile__fieldError"
                        role="alert"
                      >
                        {fieldErrors.lastName}
                      </p>
                    )}
                  </div>

                  <div className="profile__field profile__field--full">
                    <label className="profile__label" htmlFor="profile-email">
                      Email
                    </label>
                    <input
                      id="profile-email"
                      className="profile__input"
                      type="email"
                      value={form.email}
                      onChange={onFieldChange("email")}
                      autoComplete="email"
                      inputMode="email"
                      aria-required="true"
                      aria-invalid={fieldErrors.email ? "true" : "false"}
                      aria-describedby={
                        fieldErrors.email ? "profile-email-error" : undefined
                      }
                    />
                    {fieldErrors.email && (
                      <p
                        id="profile-email-error"
                        className="profile__fieldError"
                        role="alert"
                      >
                        {fieldErrors.email}
                      </p>
                    )}
                  </div>
                </div>
              </section>

              {/* ── Shipping section ── */}
              <section
                className="profile__section"
                aria-labelledby="profile-shipping-section"
              >
                <h2
                  id="profile-shipping-section"
                  className="profile__sectionTitle"
                >
                  Shipping address
                </h2>
                <p className="profile__sectionHint">
                  This address will be pre-filled at checkout.
                </p>

                <div className="profile__grid">
                  {/* Street address with Nominatim autocomplete */}
                  <div
                    className="profile__field profile__field--full"
                    ref={addressFieldRef}
                  >
                    <label
                      className="profile__label"
                      htmlFor="profile-address-line1"
                    >
                      Street address
                    </label>
                    <input
                      id="profile-address-line1"
                      className="profile__input"
                      type="text"
                      value={addressQuery}
                      onChange={onAddressChange}
                      onFocus={() => setAddressFocused(true)}
                      autoComplete="off"
                      aria-autocomplete="list"
                      aria-controls={
                        showSuggestions ? suggestionsId : undefined
                      }
                      aria-expanded={showSuggestions}
                      role="combobox"
                      placeholder="Start typing your address…"
                    />
                    {showSuggestions && (
                      <ul
                        id={suggestionsId}
                        className="profile__suggestions"
                        role="listbox"
                        aria-label="Address suggestions"
                      >
                        {suggestionsLoading ? (
                          <li
                            className="profile__suggestionItem profile__suggestionItem--loading"
                            role="option"
                            aria-selected="false"
                          >
                            Searching…
                          </li>
                        ) : (
                          suggestions.map((result, i) => (
                            <li key={i} role="option" aria-selected="false">
                              <button
                                type="button"
                                className="profile__suggestionItem"
                                onMouseDown={(e) => {
                                  // mousedown fires before blur — prevent input losing focus before click registers
                                  e.preventDefault();
                                  handleSuggestionSelect(result);
                                }}
                              >
                                {result.display_name}
                              </button>
                            </li>
                          ))
                        )}
                      </ul>
                    )}
                  </div>

                  <div className="profile__field profile__field--full">
                    <label
                      className="profile__label"
                      htmlFor="profile-apartment"
                    >
                      Apt / Unit
                    </label>
                    <input
                      id="profile-apartment"
                      className="profile__input"
                      type="text"
                      value={form.apartment}
                      onChange={onFieldChange("apartment")}
                      autoComplete="address-line2"
                    />
                  </div>

                  <div className="profile__field">
                    <label className="profile__label" htmlFor="profile-city">
                      City
                    </label>
                    <input
                      id="profile-city"
                      className="profile__input"
                      type="text"
                      value={form.city}
                      onChange={onFieldChange("city")}
                      autoComplete="address-level2"
                    />
                  </div>

                  <div className="profile__field">
                    <label className="profile__label" htmlFor="profile-state">
                      State
                    </label>
                    <input
                      id="profile-state"
                      className="profile__input"
                      type="text"
                      value={form.state}
                      onChange={onFieldChange("state")}
                      autoComplete="address-level1"
                    />
                  </div>

                  <div className="profile__field">
                    <label
                      className="profile__label"
                      htmlFor="profile-postal-code"
                    >
                      ZIP code
                    </label>
                    <input
                      id="profile-postal-code"
                      className="profile__input"
                      type="text"
                      value={form.postalCode}
                      onChange={onFieldChange("postalCode")}
                      autoComplete="postal-code"
                      inputMode="numeric"
                    />
                  </div>

                  <div className="profile__field">
                    <label
                      className="profile__label"
                      htmlFor="profile-country"
                    >
                      Country
                    </label>
                    <input
                      id="profile-country"
                      className="profile__input"
                      type="text"
                      value={form.country}
                      onChange={onFieldChange("country")}
                      autoComplete="country-name"
                    />
                  </div>
                </div>
              </section>

              <div
                className="profile__status"
                aria-live="polite"
                aria-atomic="true"
              >
                {hasStatusMessage && (
                  <>
                    {saveMsg && (
                      <div className="profile__ok" role="status">
                        {saveMsg}
                      </div>
                    )}
                    {saveErr && (
                      <div className="profile__err" role="alert">
                        {saveErr}
                      </div>
                    )}
                  </>
                )}
              </div>

              <div className="profile__actions">
                <button
                  type="submit"
                  className="profile__btn profile__btn--primary"
                  disabled={saving}
                  aria-disabled={saving}
                >
                  {saving ? "Saving…" : "Save changes"}
                </button>

                <Link
                  to="/account/change-password"
                  className="profile__btn profile__btn--secondary"
                >
                  Change password
                </Link>

                <button
                  ref={openDeleteButtonRef}
                  type="button"
                  className="profile__btn profile__btn--ghost"
                  onClick={() => setIsDeleteOpen(true)}
                  aria-haspopup="dialog"
                >
                  Delete account
                </button>
              </div>
            </form>
          )}
        </section>
      </div>

      {/* ── Delete confirmation modal ── */}
      {isDeleteOpen && (
        <div
          className="profile__modalOverlay"
          role="presentation"
          onMouseDown={() => setIsDeleteOpen(false)}
        >
          <div
            ref={modalRef}
            className="profile__modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={modalTitleId}
            aria-describedby={modalTextId}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h2 id={modalTitleId} className="profile__modalTitle">
              Delete account?
            </h2>
            <p id={modalTextId} className="profile__modalText">
              This action permanently removes your account and profile data.
            </p>

            {deleteError && (
              <div className="profile__err profile__err--modal" role="alert">
                {deleteError}
              </div>
            )}

            <div className="profile__modalActions">
              <button
                type="button"
                className="profile__btn profile__btn--primary"
                onClick={() => void handleDeleteAccount()}
                disabled={deleting}
                aria-disabled={deleting}
              >
                {deleting ? "Deleting…" : "Yes, delete"}
              </button>

              <button
                ref={deleteCancelButtonRef}
                type="button"
                className="profile__btn profile__btn--secondary"
                onClick={() => setIsDeleteOpen(false)}
                disabled={deleting}
              >
                Cancel
              </button>
            </div>

            <p className="profile__modalHint">
              Press <kbd>Esc</kbd> to close this dialog.
            </p>
          </div>
        </div>
      )}
    </main>
  );
};

export default Profile;