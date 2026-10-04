import React, { useCallback, useEffect, useId, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { loadStripe } from "@stripe/stripe-js";
import { Elements } from "@stripe/react-stripe-js";
import type { StripeElementLocale } from "@stripe/stripe-js";

import api from "../api/axiosInstance";
import CheckoutPaymentBlock from "../components/CheckoutPaymentBlock";
import Price from "../components/Price";
import ShippingRates, { type ShippingRate } from "../components/ShippingRates";
import { usePricePreview } from "../hooks/usePricePreview";
import { useAppSelector } from "../store/hooks";
import {
  clearCheckoutOrder,
  loadCheckoutOrder,
  saveCheckoutOrder,
} from "../utils/checkoutOrder";
import { PROFILE_STORAGE_KEY } from "./Profile";
import i18n from "../i18n";

import "../styles/Checkout.css";

type CartLine = {
  candle_id: number;
  variant_id?: number;
  name?: string;
  price?: number;
  image?: string;
  size?: string;
  quantity: number;
  isGift?: boolean;
};

type ShippingForm = {
  full_name: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
};

type SavedProfile = {
  firstName?: string;
  lastName?: string;
  addressLine1?: string;
  apartment?: string;
  city?: string;
  state?: string;
  postalCode?: string;
  country?: string;
};

const COUNTRIES = [
  "United States",
  "Canada",
  "United Kingdom",
  "France",
  "Germany",
  "Italy",
  "Spain",
  "Australia",
  "Japan",
  "South Korea",
  "Mexico",
  "Brazil",
  "Ukraine",
  "Russia",
];

const STATES = [
  "Alabama",
  "Alaska",
  "Arizona",
  "California",
  "Colorado",
  "Florida",
  "Georgia",
  "Illinois",
  "Massachusetts",
  "Maryland",
  "Nevada",
  "New Jersey",
  "New York",
  "North Carolina",
  "Pennsylvania",
  "Texas",
  "Virginia",
  "Washington",
  "Washington, D.C.",
];

function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}

function loadProfileFromStorage(): SavedProfile | null {
  try {
    const raw = sessionStorage.getItem(PROFILE_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function getErrorMessage(error: unknown): string {
  const fallback =
    "Could not prepare payment. Please check your information and try again.";

  if (
    typeof error !== "object" ||
    error === null ||
    !("response" in error) ||
    typeof error.response !== "object" ||
    error.response === null ||
    !("data" in error.response)
  ) {
    return fallback;
  }

  const data = error.response.data;

  if (typeof data === "string") {
    return data;
  }

  if (typeof data !== "object" || data === null) {
    return fallback;
  }

  const record = data as Record<string, unknown>;

  const shipping = record.shipping;

  if (typeof shipping === "string") {
    return shipping;
  }

  if (typeof shipping === "object" && shipping !== null) {
    const shippingRecord = shipping as Record<string, unknown>;

    for (const value of Object.values(shippingRecord)) {
      if (Array.isArray(value) && typeof value[0] === "string") {
        return value[0];
      }

      if (typeof value === "string") {
        return value;
      }
    }
  }

  const items = record.items;

  if (Array.isArray(items) && typeof items[0] === "string") {
    return items[0];
  }

  if (typeof items === "string") {
    return items;
  }

  const detail = record.detail;

  if (typeof detail === "string") {
    return detail;
  }

  return fallback;
}

/* ================= ORDER REUSE =================
   An order is defined by exactly what POST /orders/ receives: the items,
   the address and the shipping rate. If the shopper clicks again and that
   body is identical, the existing order is reused — no second stock
   reservation, and a first order keeps its welcome discount. If anything in
   it differs, the old order is cancelled (which returns its stock) and a new
   one is created. Comparing the request body is the whole rule. */

type OrderPayload = {
  items: Array<{ variant_id: number; quantity: number; is_gift: boolean }>;
  shipping: Record<string, string>;
  shipping_rate_id: string;
};

type OrderData = {
  id: number;
  status?: string;
  shipping_amount?: unknown;
  discount_amount?: unknown;
  discount_label?: unknown;
};

/** Everything the server returned for the order behind the payment form,
 *  tagged with the request that produced it. */
type PreparedOrder = {
  key: string;
  orderId: number;
  clientSecret: string;
  shipping: number;
  discount: number;
  discountLabel: string;
  tax: number;
  total: number | null;
};

/** Shown instead of the generic message: the shopper should wait, not edit. */
class CheckoutBlockedError extends Error {}

async function fetchPendingOrder(orderId: number): Promise<OrderData | null> {
  try {
    const response = await api.get(`/orders/${orderId}/`);
    return response.data?.status === "pending"
      ? { ...response.data, id: orderId }
      : null;
  } catch {
    // Gone, or belongs to whoever was signed in before: start afresh.
    return null;
  }
}

async function cancelSupersededOrder(orderId: number): Promise<void> {
  try {
    await api.post(`/orders/${orderId}/cancel/`);
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 409) {
      throw new CheckoutBlockedError(
        "Your previous payment is still being processed. Please wait a moment before changing your order."
      );
    }
    // 400 (already paid or cancelled), 404 (not this shopper's) or Stripe
    // trouble: the old order is settled, or the expiry job will cancel it.
    // Neither should stop the shopper placing the order they now want.
  }
}

async function reuseOrCreateOrder(
  payload: OrderPayload,
  key: string
): Promise<OrderData> {
  const saved = loadCheckoutOrder();

  if (saved) {
    if (saved.key === key) {
      const existing = await fetchPendingOrder(saved.orderId);
      if (existing) return existing;
    } else {
      await cancelSupersededOrder(saved.orderId);
    }

    clearCheckoutOrder();
  }

  const response = await api.post("/orders/", payload);
  const orderId = Number(response.data?.id);

  if (!orderId) {
    throw new Error("Could not create order.");
  }

  saveCheckoutOrder({ orderId, key });

  return { ...response.data, id: orderId };
}

const stripePublicKey = import.meta.env.VITE_STRIPE_PUBLIC_KEY as
  | string
  | undefined;

const stripePromise = stripePublicKey ? loadStripe(stripePublicKey) : null;

const Checkout: React.FC = () => {
  const navigate = useNavigate();

  const headingId = useId();
  const summaryId = useId();
  const shippingId = useId();
  const statusId = useId();

  const isLoggedIn = useAppSelector((state) => Boolean(state.auth?.isLoggedIn));

  const cartItems = useAppSelector(
    (state) => (state.cart.items ?? []) as CartLine[]
  );

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  /** The rate the shopper picked. Only its id travels to the server —
   *  the price is re-read from the carrier there, so a tampered amount
   *  from this page would change nothing. */
  const [selectedRate, setSelectedRate] = useState<ShippingRate | null>(null);

  /** The order behind the payment form, as the server priced it. Shipping
   *  may differ from the picked rate when the carrier API was unreachable
   *  and the server fell back to its flat rate; the discount is worked out
   *  server-side — a percentage sent from here would be forgeable. */
  const [prepared, setPrepared] = useState<PreparedOrder | null>(null);

  const savedProfile = useMemo(() => loadProfileFromStorage(), []);

  const [form, setForm] = useState<ShippingForm>({
    full_name: savedProfile
      ? [savedProfile.firstName, savedProfile.lastName]
          .filter(Boolean)
          .join(" ")
      : "",
    address_line1: savedProfile?.addressLine1 ?? "",
    address_line2: savedProfile?.apartment ?? "",
    city: savedProfile?.city ?? "",
    state: savedProfile?.state ?? "",
    postal_code: savedProfile?.postalCode ?? "",
    country: savedProfile?.country ?? "United States",
  });

  useEffect(() => {
    if (!isLoggedIn) {
      navigate("/login-choice?next=/checkout", { replace: true });
    }
  }, [isLoggedIn, navigate]);

  const items = useMemo(() => {
    return cartItems
      .map((item) => ({
        ...item,
        candle_id: Number(item.candle_id) || 0,
        variant_id: Number(item.variant_id) || 0,
        quantity: Math.max(1, Number(item.quantity) || 1),
        price: Number(item.price) || 0,
      }))
      .filter((item) => item.candle_id > 0 && item.variant_id > 0);
  }, [cartItems]);

  /** Prices for the summary before the order exists, from the same function
   *  checkout charges with. Once the order exists its own figures are used —
   *  identical, since both come from that function. */
  const previewLines = useMemo(
    () =>
      items.map((item) => ({
        variant_id: item.variant_id,
        quantity: item.quantity,
      })),
    [items]
  );
  const userId = useAppSelector((state) => state.auth?.user?.id ?? null);
  const pricing = usePricePreview(previewLines, `user:${userId ?? "?"}`);
  const preview = pricing.preview;

  const itemCount = useMemo(() => {
    return items.reduce((sum, item) => sum + item.quantity, 0);
  }, [items]);

  /** The shape the rates endpoint wants. Same lines the order will use,
   *  so the quote prices the parcel we actually ship. */
  const rateLines = useMemo(
    () =>
      items.map((item) => ({
        variant_id: item.variant_id,
        quantity: item.quantity,
      })),
    [items]
  );

  const rateAddress = useMemo(
    () => ({
      full_name: form.full_name.trim(),
      line1: form.address_line1.trim(),
      line2: form.address_line2.trim(),
      city: form.city.trim(),
      state: form.state.trim(),
      postal_code: form.postal_code.trim(),
      country: form.country.trim(),
    }),
    [form]
  );

  /** Exactly what POST /orders/ will receive. Items are sorted so the same
   *  basket always serialises the same way, whatever order it was built in. */
  const orderPayload = useMemo<OrderPayload>(
    () => ({
      items: [...items]
        .sort((a, b) => a.variant_id - b.variant_id)
        .map((item) => ({
          variant_id: item.variant_id,
          quantity: item.quantity,
          is_gift: Boolean(item.isGift),
        })),
      shipping: rateAddress,
      // Empty when the carrier API was unreachable; the server then
      // falls back to its flat rate rather than failing the sale.
      shipping_rate_id: selectedRate?.rate_id ?? "",
    }),
    [items, rateAddress, selectedRate]
  );

  const orderKey = useMemo(() => JSON.stringify(orderPayload), [orderPayload]);

  /** The prepared order only counts while the form still describes it. Any
   *  edit to the basket, address or rate takes the payment form away, so a
   *  corrected address can never be paid against the old order. */
  const current = prepared && prepared.key === orderKey ? prepared : null;

  const orderId = current?.orderId ?? null;
  const clientSecret = current?.clientSecret ?? "";
  const serverShipping = current ? current.shipping : null;
  const discount = current
    ? current.discount
    : Number(preview?.discount ?? 0) || 0;
  const discountLabel = current ? current.discountLabel : preview?.label ?? "";
  /** Items after discounts, before shipping and tax. Null until priced. */
  const itemsTotal =
    preview !== null ? Number(preview.items_total) : null;
  const tax = current ? current.tax : null;
  const total = current ? current.total : null;

  // Stable identity, or ShippingRates would rebuild its fetch on every
  // render and defeat the debounce.
  const handleRateSelect = useCallback((rate: ShippingRate | null) => {
    setSelectedRate(rate);
  }, []);

  const onFieldChange =
    (key: keyof ShippingForm) =>
    (event: React.ChangeEvent<HTMLInputElement>): void => {
      setForm((prev) => ({
        ...prev,
        [key]: event.target.value,
      }));
    };

  const canPreparePayment =
    items.length > 0 &&
    form.full_name.trim().length > 0 &&
    form.address_line1.trim().length > 0 &&
    form.city.trim().length > 0 &&
    form.state.trim().length > 0 &&
    form.postal_code.trim().length > 0 &&
    form.country.trim().length > 0;

  const showPayment = Boolean(clientSecret) && orderId !== null;

  /** Before the order exists, the picked rate is the best estimate.
   *  After it, the server's number is the truth. */
  const shippingToShow =
    serverShipping !== null
      ? serverShipping
      : selectedRate
        ? Number(selectedRate.amount)
        : null;

  const stripeOptions = useMemo(() => {
    if (!clientSecret) return undefined;

    const currentLanguage = i18n.language?.split("-")[0];

    const stripeLocale: StripeElementLocale =
      currentLanguage === "ru" ||
      currentLanguage === "es" ||
      currentLanguage === "fr"
        ? currentLanguage
        : "en";

    return {
      clientSecret,
      locale: stripeLocale,
      appearance: {
        theme: "stripe" as const,
      },
    };
  }, [clientSecret]);

  const createOrderAndIntent = async (): Promise<void> => {
    if (!canPreparePayment || loading) return;

    // Captured now: the form can change while the requests are in flight,
    // and the result must be tagged with the request that produced it.
    const payload = orderPayload;
    const key = orderKey;

    setLoading(true);
    setErrorMsg("");
    setPrepared(null);

    try {
      const order = await reuseOrCreateOrder(payload, key);

      const intentResponse = await api.post("/orders/create-intent/", {
        order_id: order.id,
      });

      const clientSecretValue = intentResponse.data?.client_secret;

      if (typeof clientSecretValue !== "string" || !clientSecretValue.trim()) {
        throw new Error("Payment initialization failed.");
      }

      setPrepared({
        key,
        orderId: order.id,
        clientSecret: clientSecretValue,
        shipping: Number(order.shipping_amount) || 0,
        discount: Number(order.discount_amount) || 0,
        discountLabel: String(order.discount_label ?? ""),
        tax: Number(intentResponse.data?.tax_amount) || 0,
        total: Number(intentResponse.data?.total_amount) || null,
      });
    } catch (error) {
      console.error("Checkout error:", error);
      setErrorMsg(
        error instanceof CheckoutBlockedError
          ? error.message
          : getErrorMessage(error)
      );
    } finally {
      setLoading(false);
    }
  };

  if (!isLoggedIn) return null;

  return (
    <main className="checkout" aria-labelledby={headingId}>
      <div className="checkout__inner">
        <datalist id="country-options">
          {COUNTRIES.map((country) => (
            <option key={country} value={country} />
          ))}
        </datalist>

        <datalist id="state-options">
          {STATES.map((state) => (
            <option key={state} value={state} />
          ))}
        </datalist>

        <div className="checkout__backWrap">
          <Link to="/cart" className="checkout__backLink">
            ← Go back to shopping cart
          </Link>
        </div>

        <header className="checkout__header">
          <h1 id={headingId} className="checkout__title">
            Place your order
          </h1>

          <p className="checkout__subtitle">
            Review your items, enter your shipping details, and continue to
            secure payment.
          </p>
        </header>

        <div
          id={statusId}
          className="checkout__statusArea checkout__statusArea--page"
          aria-live="polite"
          aria-atomic="true"
        >
          {orderId !== null && (
            <div className="checkout__state">Order #{orderId} created.</div>
          )}

          {clientSecret && (
            <div className="checkout__state">Payment is ready.</div>
          )}

          {errorMsg && (
            <div className="checkout__state checkout__state--error" role="alert">
              {errorMsg}
            </div>
          )}
        </div>

        <div className="checkout__grid">
          <section className="checkout__summary" aria-labelledby={summaryId}>
            <h2 id={summaryId} className="checkout__sectionTitle">
              Order summary
            </h2>

            <ul className="checkout__items" role="list">
              {items.map((item) => {
                const name = item.name?.trim() || `Candle #${item.candle_id}`;
                const priced = pricing.line(item.variant_id);

                return (
                  <li
                    key={`${item.candle_id}-${item.variant_id}`}
                    className="checkoutItem"
                  >
                    {item.image ? (
                      <img
                        src={item.image}
                        alt={name}
                        className="checkoutItem__image"
                      />
                    ) : (
                      <div className="checkoutItem__image checkoutItem__image--empty" />
                    )}

                    <div className="checkoutItem__info">
                      <h3 className="checkoutItem__name">{name}</h3>

                      {item.size && (
                        <p className="checkoutItem__meta">Size: {item.size}</p>
                      )}

                      <p className="checkoutItem__meta">
                        Quantity: {item.quantity}
                      </p>

                      {item.isGift && (
                        <p className="checkoutItem__meta">
                          Gift option included
                        </p>
                      )}
                    </div>

                    <div className="checkoutItem__lineTotal">
                      {priced ? (
                        <Price
                          price={priced.line_total}
                          discountPrice={priced.line_total_after_discount}
                        />
                      ) : (
                        "—"
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>

            <div className="checkout__totals">
              <div className="checkout__totalRow">
                <span>Items</span>
                <span>{itemCount}</span>
              </div>

              <div className="checkout__totalRow">
                <span>Subtotal</span>
                <span>
                  {preview ? money(Number(preview.subtotal)) : "—"}
                </span>
              </div>

              {discount > 0 && (
                <div className="checkout__totalRow checkout__totalRow--discount">
                  <span>{discountLabel || "Discount"}</span>
                  <span>−{money(discount)}</span>
                </div>
              )}

              <div className="checkout__totalRow">
                <span>
                  Shipping
                  {selectedRate && serverShipping === null && (
                    <span className="checkout__totalNote">
                      {" "}
                      {selectedRate.carrier} {selectedRate.service_level}
                    </span>
                  )}
                </span>
                <span>
                  {shippingToShow === null ? "—" : money(shippingToShow)}
                </span>
              </div>

              <div className="checkout__totalRow">
                <span>Tax</span>
                <span>{tax === null ? "—" : money(tax)}</span>
              </div>

              <div className="checkout__totalRow checkout__totalRow--grand">
                <span>Total</span>
                <span>
                  {total !== null
                    ? money(total)
                    : itemsTotal === null
                      ? "—"
                      : shippingToShow === null
                        ? money(itemsTotal)
                        : money(itemsTotal + shippingToShow)}
                </span>
              </div>
            </div>
          </section>

          <section className="checkout__formPanel" aria-labelledby={shippingId}>
            <h2 id={shippingId} className="checkout__sectionTitle">
              {showPayment ? "Payment" : "Shipping details"}
            </h2>

            {!showPayment ? (
              <form
                className="checkoutForm"
                onSubmit={(event) => {
                  event.preventDefault();
                  void createOrderAndIntent();
                }}
                noValidate
              >
                <div className="checkoutForm__group">
                  <label
                    className="checkoutForm__label"
                    htmlFor="checkout-full-name"
                  >
                    Full name
                  </label>

                  <input
                    id="checkout-full-name"
                    className="checkoutForm__input"
                    type="text"
                    autoComplete="name"
                    value={form.full_name}
                    onChange={onFieldChange("full_name")}
                    disabled={loading}
                    placeholder="John Smith"
                  />
                </div>

                <div className="checkoutForm__group">
                  <label
                    className="checkoutForm__label"
                    htmlFor="checkout-address-1"
                  >
                    Street address
                  </label>

                  <input
                    id="checkout-address-1"
                    className="checkoutForm__input"
                    type="text"
                    autoComplete="address-line1"
                    value={form.address_line1}
                    onChange={onFieldChange("address_line1")}
                    disabled={loading}
                    placeholder="123 Madison Ave"
                  />
                </div>

                <div className="checkoutForm__row">
                  <div className="checkoutForm__group">
                    <label
                      className="checkoutForm__label"
                      htmlFor="checkout-address-2"
                    >
                      Apt / Unit
                    </label>

                    <input
                      id="checkout-address-2"
                      className="checkoutForm__input"
                      type="text"
                      autoComplete="address-line2"
                      value={form.address_line2}
                      onChange={onFieldChange("address_line2")}
                      disabled={loading}
                      placeholder="Apartment 4B"
                    />
                  </div>

                  <div className="checkoutForm__group">
                    <label
                      className="checkoutForm__label"
                      htmlFor="checkout-city"
                    >
                      City
                    </label>

                    <input
                      id="checkout-city"
                      className="checkoutForm__input"
                      type="text"
                      autoComplete="address-level2"
                      value={form.city}
                      onChange={onFieldChange("city")}
                      disabled={loading}
                      placeholder="New York"
                    />
                  </div>
                </div>

                <div className="checkoutForm__row">
                  <div className="checkoutForm__group">
                    <label
                      className="checkoutForm__label"
                      htmlFor="checkout-state"
                    >
                      State / Region
                    </label>

                    <input
                      id="checkout-state"
                      className="checkoutForm__input"
                      type="text"
                      autoComplete="address-level1"
                      list="state-options"
                      value={form.state}
                      onChange={onFieldChange("state")}
                      disabled={loading}
                      placeholder="California"
                    />
                  </div>

                  <div className="checkoutForm__group">
                    <label
                      className="checkoutForm__label"
                      htmlFor="checkout-postal-code"
                    >
                      ZIP / Postal code
                    </label>

                    <input
                      id="checkout-postal-code"
                      className="checkoutForm__input"
                      type="text"
                      autoComplete="postal-code"
                      value={form.postal_code}
                      onChange={onFieldChange("postal_code")}
                      disabled={loading}
                      placeholder="10001"
                    />
                  </div>
                </div>

                <div className="checkoutForm__group">
                  <label
                    className="checkoutForm__label"
                    htmlFor="checkout-country"
                  >
                    Country
                  </label>

                  <input
                    id="checkout-country"
                    className="checkoutForm__input"
                    type="text"
                    autoComplete="country-name"
                    list="country-options"
                    value={form.country}
                    onChange={onFieldChange("country")}
                    disabled={loading}
                    placeholder="United States"
                  />
                </div>

                <ShippingRates
                  address={rateAddress}
                  items={rateLines}
                  selectedRateId={selectedRate?.rate_id ?? ""}
                  disabled={loading}
                  onSelect={handleRateSelect}
                />

                <button
                  type="submit"
                  className="checkout__button"
                  disabled={loading || !canPreparePayment}
                >
                  {loading ? "Preparing payment..." : "Continue to payment"}
                </button>
              </form>
            ) : stripePromise && stripeOptions ? (
              <Elements stripe={stripePromise} options={stripeOptions}>
                <CheckoutPaymentBlock
                  orderId={orderId!}
                  clientSecret={clientSecret}
                />
              </Elements>
            ) : (
              <div className="checkout__state checkout__state--error">
                Stripe is not configured correctly.
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
};

export default Checkout;