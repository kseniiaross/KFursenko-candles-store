import axios from "axios";

import api from "./axiosInstance";
import type { CartLine } from "../store/cartSlice";

/** Cart requests run one at a time, in the order they were made. Every
 *  response is the whole cart; run side by side, a slow early answer could
 *  land after a later one and put back a cart the server no longer has. */
let queue: Promise<unknown> = Promise.resolve();

function inOrder<T>(request: () => Promise<T>): Promise<T> {
  const run = queue.then(request, request);
  queue = run.catch(() => undefined);
  return run;
}

/** The server's reason for refusing a cart change, in words the shopper
 *  can act on, or a general one when it gave none. */
export function readCartError(error: unknown): string {
  const fallback = "We couldn't update your cart. Please try again.";

  if (!axios.isAxiosError(error)) return fallback;

  const data: unknown = error.response?.data;

  if (!data || typeof data !== "object") return fallback;

  for (const key of ["quantity", "variant_id", "items", "detail"]) {
    const value = (data as Record<string, unknown>)[key];

    if (typeof value === "string") return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  }

  return fallback;
}

type CartApiItem = {
  item_id: number | string;
  variant_id: number | string;
  candle_id: number | string;
  name: string;
  slug: string;
  image?: string | null;
  price: string | number;
  size: string;
  quantity: number | string;
  in_stock: boolean;
  is_gift: boolean;
};

type CartApiResponse = {
  id: number;
  items: CartApiItem[];
  created_at: string;
  updated_at: string;
};

export type AddToCartPayload = {
  variant_id: number;
  quantity: number;
  is_gift?: boolean;
};

export type UpdateCartItemPayload = {
  quantity?: number;
  is_gift?: boolean;
};

export type MergeCartPayload = {
  items: Array<{
    variant_id: number;
    quantity: number;
    is_gift?: boolean;
  }>;
};

function toNumber(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function mapCartItem(item: CartApiItem): CartLine {
  return {
    item_id: toNumber(item.item_id),
    variant_id: toNumber(item.variant_id),
    candle_id: toNumber(item.candle_id),
    name: item.name,
    price: toNumber(item.price),
    image: item.image ?? undefined,
    size: item.size,
    quantity: Math.max(1, toNumber(item.quantity) || 1),
    isGift: Boolean(item.is_gift),
    inStock: Boolean(item.in_stock),
  };
}

export function mapCartResponse(data: CartApiResponse): CartLine[] {
  if (!data || !Array.isArray(data.items)) {
    return [];
  }

  return data.items
    .map(mapCartItem)
    .filter((item) => item.item_id && item.variant_id && item.candle_id);
}

export async function getMyCart(): Promise<CartLine[]> {
  const response = await inOrder(() => api.get<CartApiResponse>("/cart/my/"));
  return mapCartResponse(response.data);
}

export async function addToCart(payload: AddToCartPayload): Promise<CartLine[]> {
  const response = await inOrder(() =>
    api.post<CartApiResponse>("/cart/items/add/", {
      variant_id: Number(payload.variant_id),
      quantity: Math.max(1, Number(payload.quantity) || 1),
      is_gift: Boolean(payload.is_gift),
    })
  );

  return mapCartResponse(response.data);
}

export async function patchCartItem(
  itemId: number,
  payload: UpdateCartItemPayload
): Promise<CartLine[]> {
  const response = await inOrder(() =>
    api.patch<CartApiResponse>(`/cart/items/${Number(itemId)}/`, payload)
  );

  return mapCartResponse(response.data);
}

export async function deleteCartItem(itemId: number): Promise<CartLine[]> {
  const response = await inOrder(() =>
    api.delete<CartApiResponse>(`/cart/items/${Number(itemId)}/delete/`)
  );

  return mapCartResponse(response.data);
}

export async function mergeCart(payload: MergeCartPayload): Promise<CartLine[]> {
  const response = await inOrder(() =>
    api.post<CartApiResponse>("/cart/merge/", {
      items: payload.items.map((item) => ({
        variant_id: Number(item.variant_id),
        quantity: Math.max(1, Number(item.quantity) || 1),
        is_gift: Boolean(item.is_gift),
      })),
    })
  );

  return mapCartResponse(response.data);
}

export async function clearServerCart(): Promise<CartLine[]> {
  const response = await inOrder(() => api.delete<CartApiResponse>("/cart/clear/"));
  return mapCartResponse(response.data);
}