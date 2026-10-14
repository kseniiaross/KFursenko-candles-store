import { createSlice } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";

import { logout } from "./authSlice";

export type CartLine = {
  item_id?: number;
  variant_id: number;
  candle_id: number;
  name?: string;
  price: number;
  image?: string;
  size?: string;
  quantity: number;
  isGift?: boolean;
  /** From the server cart only: false once the candle has sold out or been
   *  switched off. A guest's cart doesn't know. */
  inStock?: boolean;
};

/** The most of one candle a line can hold — the cap order creation and the
 *  price preview enforce (cart.models.MAX_LINE_QUANTITY on the server). */
export const MAX_LINE_QUANTITY = 999;

function clampQuantity(value: unknown): number {
  return Math.min(MAX_LINE_QUANTITY, Math.max(1, Number(value) || 1));
}

type CartState = {
  items: CartLine[];
  /** What signing in changed in the cart (a candle sold out, switched off
   *  or lowered to what's left), until the shopper dismisses it. */
  notices: string[];
};

/** Whether a change should be written to the guest copy in localStorage.
 *  Only a guest's cart lives there; a signed-in cart lives on the server,
 *  and writing it here gets merged back into the server cart on the next
 *  load — counting every line twice. The slice cannot see auth state, so
 *  the caller decides, and the field is required so none can forget. */
type GuestPersistence = { persistAsGuest: boolean };

export const GUEST_CART_KEY = "guest_cart_items";
const STORAGE_KEY = GUEST_CART_KEY;

/* ================= STORAGE ================= */

function normalizeCartLine(item: CartLine): CartLine {
  return {
    ...item,
    item_id: item.item_id ? Number(item.item_id) : undefined,
    variant_id: Number(item.variant_id) || 0,
    candle_id: Number(item.candle_id) || 0,
    quantity: clampQuantity(item.quantity),
    price: Number(item.price) || 0,
    isGift: Boolean(item.isGift),
  };
}

function loadGuestCart(): CartLine[] {
  if (typeof window === "undefined") return [];

  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];

    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed
      .map((item) => normalizeCartLine(item as CartLine))
      .filter((item) => item.variant_id > 0 && item.candle_id > 0);
  } catch {
    return [];
  }
}

function saveGuestCart(items: CartLine[]): void {
  if (typeof window === "undefined") return;

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Ignore storage failures.
  }
}

function clearGuestCartStorageInternal(): void {
  if (typeof window === "undefined") return;

  try {
    localStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}

/** Sign-in notices are kept for the tab, so a reload doesn't lose one
 *  the shopper hasn't read; OK or closing the tab ends them. */
const NOTICES_KEY = "cart_notices";

function loadNotices(): string[] {
  if (typeof window === "undefined") return [];

  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(NOTICES_KEY) || "[]");
    return Array.isArray(parsed)
      ? parsed.filter((notice): notice is string => typeof notice === "string")
      : [];
  } catch {
    return [];
  }
}

function saveNotices(notices: string[]): void {
  if (typeof window === "undefined") return;

  try {
    if (notices.length > 0) {
      sessionStorage.setItem(NOTICES_KEY, JSON.stringify(notices));
    } else {
      sessionStorage.removeItem(NOTICES_KEY);
    }
  } catch {
    // Ignore storage failures; the notice still shows until a reload.
  }
}

export function getGuestCartStorage(): CartLine[] {
  return loadGuestCart();
}

export function clearGuestCartStorage(): void {
  clearGuestCartStorageInternal();
}

/* ================= HELPERS ================= */

function findIndex(items: CartLine[], variant_id: number): number {
  return items.findIndex((item) => Number(item.variant_id) === Number(variant_id));
}

/* ================= SLICE ================= */

const initialState: CartState = {
  items: loadGuestCart(),
  notices: loadNotices(),
};

const cartSlice = createSlice({
  name: "cart",
  initialState,
  reducers: {
    // Important:
    // setCart is for server cart / Redux memory.
    // It must NOT save to guest localStorage.
    setCart: (state, action: PayloadAction<CartLine[]>) => {
      state.items = (action.payload ?? [])
        .map(normalizeCartLine)
        .filter((item) => item.variant_id > 0 && item.candle_id > 0);
    },

    setGuestCart: (state, action: PayloadAction<CartLine[]>) => {
      state.items = (action.payload ?? [])
        .map(normalizeCartLine)
        .filter((item) => item.variant_id > 0 && item.candle_id > 0);

      saveGuestCart(state.items);
    },

    addToCart: (
      state,
      action: PayloadAction<{ item: CartLine } & GuestPersistence>
    ) => {
      const item = normalizeCartLine(action.payload.item);

      if (!item.variant_id || !item.candle_id) return;

      const idx = findIndex(state.items, item.variant_id);

      if (idx === -1) {
        state.items.push(item);
      } else {
        state.items[idx].quantity = clampQuantity(
          state.items[idx].quantity + item.quantity
        );
      }

      if (action.payload.persistAsGuest) saveGuestCart(state.items);
    },

    updateQty: (
      state,
      action: PayloadAction<{
        variant_id: number;
        quantity: number;
      } & GuestPersistence>
    ) => {
      const variant_id = Number(action.payload.variant_id) || 0;
      const idx = findIndex(state.items, variant_id);

      if (idx === -1) return;

      state.items[idx].quantity = clampQuantity(action.payload.quantity);
      if (action.payload.persistAsGuest) saveGuestCart(state.items);
    },

    setGiftOption: (
      state,
      action: PayloadAction<{
        variant_id: number;
        isGift: boolean;
      } & GuestPersistence>
    ) => {
      const variant_id = Number(action.payload.variant_id) || 0;
      const idx = findIndex(state.items, variant_id);

      if (idx === -1) return;

      state.items[idx].isGift = Boolean(action.payload.isGift);
      if (action.payload.persistAsGuest) saveGuestCart(state.items);
    },

    removeFromCart: (
      state,
      action: PayloadAction<{
        variant_id: number;
      } & GuestPersistence>
    ) => {
      const variant_id = Number(action.payload.variant_id) || 0;

      state.items = state.items.filter(
        (item) => Number(item.variant_id) !== variant_id
      );

      if (action.payload.persistAsGuest) saveGuestCart(state.items);
    },

    setCartNotices: (state, action: PayloadAction<string[]>) => {
      state.notices = action.payload;
      saveNotices(state.notices);
    },

    dismissCartNotices: (state) => {
      state.notices = [];
      saveNotices(state.notices);
    },

    clearCart: (state) => {
      state.items = [];
      clearGuestCartStorageInternal();
    },
  },

  extraReducers: (builder) => {
    // Signing out leaves the server cart in memory. Without this, the next
    // guest change would save those lines as the guest cart and the next
    // sign-in would merge them back in a second time. The server keeps the
    // cart; it returns on the next sign-in.
    builder.addCase(logout, (state) => {
      state.items = [];
      state.notices = [];
      saveNotices(state.notices);
    });
  },
});

export const {
  setCart,
  setGuestCart,
  addToCart,
  updateQty,
  setGiftOption,
  removeFromCart,
  setCartNotices,
  dismissCartNotices,
  clearCart,
} = cartSlice.actions;

export default cartSlice.reducer;