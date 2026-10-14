import api from "../api/axiosInstance";
import type { Order } from "../types/orders";

export type CreateOrderPayload = {
  items: Array<{
    variant_id: number;
    quantity: number;
    is_gift?: boolean;
  }>;
  shipping?: {
    full_name: string;
    line1: string;
    line2?: string;
    city: string;
    state: string;
    postal_code: string;
    country: string;
  };
  shipping_amount?: number;
};

export async function createOrder(payload: CreateOrderPayload): Promise<Order> {
  const resp = await api.post<Order>("/orders/", payload);
  return resp.data;
}

export async function createOrderFromCart(): Promise<Order> {
  const resp = await api.post<Order>("/orders/from-cart/", {});
  return resp.data;
}

export async function listMyOrders(): Promise<Order[]> {
  const resp = await api.get<Order[]>("/orders/my/");
  return resp.data;
}

export async function getMyOrderById(id: number): Promise<Order> {
  const resp = await api.get<Order>(`/orders/${id}/`);
  return resp.data;
}

export async function listStaffOrders(): Promise<Order[]> {
  const resp = await api.get<Order[]>("/orders/staff/");
  return resp.data;
}

export async function staffUpdateOrderStatus(
  id: number,
  statusValue: string
): Promise<Order> {
  const resp = await api.patch<Order>(`/orders/${id}/status/`, {
    status: statusValue,
  });

  return resp.data;
}
export type WelcomeOffer = {
  title: string;
  discount_percent: number;
  /** null when the offer doesn't run out for a new account. */
  days_after_signup: number | null;
};

/** The sign-up discount running now, or null when there isn't one. */
export async function getWelcomeOffer(): Promise<WelcomeOffer | null> {
  const resp = await api.get<{ welcome_offer: WelcomeOffer | null }>(
    "/orders/welcome-offer/"
  );
  return resp.data.welcome_offer ?? null;
}
