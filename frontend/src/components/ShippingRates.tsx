import React, { useCallback, useEffect, useRef, useState } from "react";

import api from "../api/axiosInstance";
import "../styles/ShippingRates.css";

export type ShippingRate = {
  rate_id: string;
  carrier: string;
  service_level: string;
  amount: string;
  currency: string;
  estimated_days: number | null;
  duration_terms: string;
};

export type RateAddress = {
  full_name: string;
  line1: string;
  line2?: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
};

export type RateLine = {
  variant_id: number;
  quantity: number;
};

type Props = {
  address: RateAddress;
  /** Must be the same lines the order will be built from. Quoting the
   *  server-side cart while the order comes from Redux would price a
   *  different parcel than the one we ship. */
  items: RateLine[];
  selectedRateId: string;
  disabled?: boolean;
  onSelect: (rate: ShippingRate | null) => void;
};

/** Enough of an address to price a parcel. Asking Shippo before this is
 *  filled in just burns rate-limit budget on a guaranteed error. */
function isQuotable(address: RateAddress): boolean {
  return Boolean(
    address.line1?.trim() &&
      address.city?.trim() &&
      address.state?.trim() &&
      address.postal_code?.trim() &&
      address.country?.trim()
  );
}

function formatEta(rate: ShippingRate): string {
  if (rate.estimated_days === null) return rate.duration_terms || "";
  if (rate.estimated_days === 1) return "Arrives in about 1 business day";
  return `Arrives in about ${rate.estimated_days} business days`;
}

function readError(error: unknown): string {
  const fallback =
    "We could not price this address. Please check it and try again.";

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

  const data = error.response.data as Record<string, unknown> | string | null;

  if (typeof data === "string") return data;
  if (!data) return fallback;

  const shipping = data.shipping;
  if (typeof shipping === "string") return shipping;
  if (Array.isArray(shipping) && typeof shipping[0] === "string") {
    return shipping[0];
  }

  const detail = data.detail;
  if (typeof detail === "string") return detail;

  return fallback;
}

const ShippingRates: React.FC<Props> = ({
  address,
  items,
  selectedRateId,
  disabled = false,
  onSelect,
}) => {
  const [rates, setRates] = useState<ShippingRate[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(
    "idle"
  );
  const [error, setError] = useState("");

  /** Bumped on every request. A slow earlier response must not overwrite a
   *  newer one — otherwise a fast typist sees prices for a previous ZIP. */
  const requestId = useRef(0);

  // Read through refs so the fetch always sees current values without
  // being rebuilt on every keystroke.
  const addressRef = useRef(address);
  addressRef.current = address;

  const itemsRef = useRef(items);
  itemsRef.current = items;

  const selectedRef = useRef(selectedRateId);
  selectedRef.current = selectedRateId;

  const fetchRates = useCallback(async () => {
    const id = ++requestId.current;

    setStatus("loading");
    setError("");

    try {
      const response = await api.post("/shipping/rates/", {
        shipping: addressRef.current,
        items: itemsRef.current,
      });

      if (id !== requestId.current) return;

      const data = (response.data ?? []) as ShippingRate[];

      setRates(data);
      setStatus("ready");

      // Preselect the cheapest so the total is never blank.
      if (data.length && !data.some((r) => r.rate_id === selectedRef.current)) {
        onSelect(data[0]);
      }
    } catch (err) {
      if (id !== requestId.current) return;

      setStatus("error");
      setError(readError(err));
      setRates([]);
      onSelect(null);
    }
  }, [onSelect]);

  const itemsKey = items
    .map((line) => `${line.variant_id}x${line.quantity}`)
    .join(",");

  useEffect(() => {
    if (!isQuotable(address) || items.length === 0) {
      setRates([]);
      setStatus("idle");
      onSelect(null);
      return;
    }

    // Each keystroke would otherwise be a live call to a carrier API.
    const timer = setTimeout(() => void fetchRates(), 600);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    address.line1,
    address.line2,
    address.city,
    address.state,
    address.postal_code,
    address.country,
    itemsKey,
  ]);

  return (
    <div className="rates">
      <h3 className="rates__title">Delivery option</h3>

      {status === "idle" && (
        <p className="rates__hint">
          Fill in your address and delivery options will appear here.
        </p>
      )}

      {status === "loading" && (
        <ul className="rates__list" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <li key={i} className="rates__skeleton" />
          ))}
        </ul>
      )}

      {status === "error" && (
        <>
          <p className="rates__error" role="alert">
            {error}
          </p>
          <button
            type="button"
            className="rates__retry"
            onClick={() => void fetchRates()}
          >
            Try again
          </button>
        </>
      )}

      {status === "ready" && rates.length > 0 && (
        <>
          <ul
            className="rates__list"
            role="radiogroup"
            aria-label="Shipping options"
          >
            {rates.map((rate) => {
              const isSelected = rate.rate_id === selectedRateId;

              return (
                <li key={rate.rate_id}>
                  <label
                    className={`rates__option${
                      isSelected ? " rates__option--selected" : ""
                    }`}
                  >
                    <input
                      type="radio"
                      name="shipping-rate"
                      className="rates__radio"
                      checked={isSelected}
                      disabled={disabled}
                      onChange={() => onSelect(rate)}
                    />

                    <span className="rates__body">
                      <span className="rates__carrier">{rate.carrier}</span>
                      <span className="rates__service">
                        {rate.service_level}
                      </span>
                      <span className="rates__eta">{formatEta(rate)}</span>
                    </span>

                    <span className="rates__price">
                      ${Number(rate.amount).toFixed(2)}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>

          <p className="rates__note">
            Rates come straight from the carrier — we do not add a markup.
          </p>
        </>
      )}
    </div>
  );
};

export default ShippingRates;