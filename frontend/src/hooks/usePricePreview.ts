import { useEffect, useMemo, useRef, useState } from "react";

import api from "../api/axiosInstance";

/** One basket line as the server prices it. Amounts are decimal strings. */
export type PreviewLine = {
  variant_id: number;
  unit_price: string;
  quantity: number;
  line_total: string;
  discount_amount: string;
  discount_label: string;
  /** Units on this line given free by buy-two-get-three. */
  free_quantity: number;
  /** On a free line: the welcome offer the lines that paid for it would
   *  otherwise have had. Empty otherwise. */
  replaces_label: string;
  line_total_after_discount: string;
};

export type BasketPreview = {
  lines: PreviewLine[];
  subtotal: string;
  discount: string;
  /** Items after discounts; shipping and tax come on top. */
  items_total: string;
  /** Every promotion that applied, joined. Empty when none did. */
  label: string;
  /** Variant ids that no longer exist or are switched off. Not priced. */
  unavailable: number[];
};

type BasketLine = { variant_id: number; quantity: number };

type PricePreview = {
  /** The latest answer the server gave; kept while a newer one loads. */
  preview: BasketPreview | null;
  /** A request for the current basket is in flight. */
  updating: boolean;
  /** The last request failed. The page must not work prices out itself. */
  failed: boolean;
  /** This variant's line in the preview, if priced. */
  line: (variantId: number) => PreviewLine | undefined;
};

/**
 * Prices a basket with POST /api/orders/price-preview/ — the same function
 * checkout charges with — instead of multiplying prices in the browser.
 *
 * Re-asks whenever the variants or quantities change, or whoever is signed
 * in changes (the welcome offer depends on it). A slow response can't
 * overwrite a newer one.
 */
export function usePricePreview(
  items: BasketLine[],
  shopperKey: string
): PricePreview {
  const [preview, setPreview] = useState<BasketPreview | null>(null);
  // Which basket (and shopper) the current preview, or the last failure,
  // belongs to. "Updating" is derived from these rather than set, so the
  // effect below only ever sets state when the server answers.
  const [answeredKey, setAnsweredKey] = useState<string | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);
  const requestId = useRef(0);

  // Stable identity for the basket, so re-renders that don't change it
  // don't re-ask.
  const basketKey = useMemo(
    () =>
      items
        .map((item) => `${item.variant_id}x${item.quantity}`)
        .sort()
        .join(","),
    [items]
  );

  const requestKey = `${basketKey}|${shopperKey}`;

  useEffect(() => {
    const id = ++requestId.current;
    const lines = basketKey
      ? basketKey.split(",").map((part) => {
          const [variant, quantity] = part.split("x");
          return { variant_id: Number(variant), quantity: Number(quantity) };
        })
      : [];

    api
      .post<BasketPreview>("/orders/price-preview/", { items: lines })
      .then((response) => {
        if (id !== requestId.current) return;
        setPreview(response.data);
        setAnsweredKey(requestKey);
        setFailedKey(null);
      })
      .catch((error: unknown) => {
        if (id !== requestId.current) return;
        console.error("Could not price the basket:", error);
        setFailedKey(requestKey);
      });
  }, [basketKey, requestKey]);

  const byVariant = useMemo(
    () => new Map((preview?.lines ?? []).map((line) => [line.variant_id, line])),
    [preview]
  );

  const failed = failedKey === requestKey;

  return {
    preview,
    updating: answeredKey !== requestKey && !failed,
    failed,
    line: (variantId) => byVariant.get(variantId),
  };
}
