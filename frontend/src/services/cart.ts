import api from "../api/axiosInstance";
import type { Cart } from "../types/orders";

export type AddToCartPayload = {
  candle_id: number;
  quantity: number;
};

export type UpdateCartItemPayload = {
  quantity: number;
};

export async function getMyCart(): Promise<Cart> {
  const resp = await api.get<Cart>("/cart/my/");
  return resp.data;
}

export async function addToCart(payload: AddToCartPayload): Promise<Cart> {
  const resp = await api.post<Cart>("/cart/items/add/", payload);
  return resp.data;
}

export async function updateCartItem(itemId: number, payload: UpdateCartItemPayload): Promise<Cart> {
  const resp = await api.put<Cart>(`/cart/items/${itemId}/`, payload);
  return resp.data;
}

export async function patchCartItem(itemId: number, payload: Partial<UpdateCartItemPayload>): Promise<Cart> {
  const resp = await api.patch<Cart>(`/cart/items/${itemId}/`, payload);
  return resp.data;
}

export async function deleteCartItem(itemId: number): Promise<void> {
  await api.delete(`/cart/items/${itemId}/delete/`);
}

export type MergeCartPayload = {
  items: Array<{ candle_id: number; quantity: number }>;
};

export async function mergeCart(payload: MergeCartPayload): Promise<Cart> {
  const resp = await api.post<Cart>("/cart/merge/", payload);
  return resp.data;
}