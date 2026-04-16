import { createSlice } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";

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
};

type CartState = {
  items: CartLine[];
};

const GUEST_CART_STORAGE_KEY = "guest_cart_items";

function loadGuestCart(): CartLine[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = localStorage.getItem(GUEST_CART_STORAGE_KEY);

    if (!raw) {
      return [];
    }

    const parsed: unknown = JSON.parse(raw);

    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed as CartLine[];
  } catch {
    return [];
  }
}

function saveGuestCart(items: CartLine[]): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    localStorage.setItem(GUEST_CART_STORAGE_KEY, JSON.stringify(items));
  } catch {
    // ignore storage failures
  }
}

export function getGuestCartStorage(): CartLine[] {
  return loadGuestCart();
}

export function clearGuestCartStorage(): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    localStorage.removeItem(GUEST_CART_STORAGE_KEY);
  } catch {
    // ignore storage failures
  }
}

const initialState: CartState = {
  items: loadGuestCart(),
};

function findIndex(items: CartLine[], variant_id: number): number {
  return items.findIndex((item) => item.variant_id === variant_id);
}

const cartSlice = createSlice({
  name: "cart",
  initialState,
  reducers: {
    setCart: (state, action: PayloadAction<CartLine[]>) => {
      state.items = action.payload ?? [];
      saveGuestCart(state.items);
    },

    addToCart: (state, action: PayloadAction<CartLine>) => {
      const { variant_id } = action.payload;
      const idx = findIndex(state.items, variant_id);
      const qty = Math.max(1, action.payload.quantity ?? 1);

      if (idx === -1) {
        state.items.push({
          ...action.payload,
          quantity: qty,
          isGift: Boolean(action.payload.isGift),
        });
      } else {
        state.items[idx].quantity += qty;
      }

      saveGuestCart(state.items);
    },

    updateQty: (
      state,
      action: PayloadAction<{
        variant_id: number;
        quantity: number;
      }>
    ) => {
      const idx = findIndex(state.items, action.payload.variant_id);

      if (idx === -1) {
        return;
      }

      state.items[idx].quantity = Math.max(1, action.payload.quantity);
      saveGuestCart(state.items);
    },

    setGiftOption: (
      state,
      action: PayloadAction<{
        variant_id: number;
        isGift: boolean;
      }>
    ) => {
      const idx = findIndex(state.items, action.payload.variant_id);

      if (idx === -1) {
        return;
      }

      state.items[idx].isGift = action.payload.isGift;
      saveGuestCart(state.items);
    },

    removeFromCart: (
      state,
      action: PayloadAction<{
        variant_id: number;
      }>
    ) => {
      state.items = state.items.filter(
        (item) => item.variant_id !== action.payload.variant_id
      );

      saveGuestCart(state.items);
    },

    clearCart: (state) => {
      state.items = [];
      clearGuestCartStorage();
    },
  },
});

export const {
  setCart,
  addToCart,
  updateQty,
  setGiftOption,
  removeFromCart,
  clearCart,
} = cartSlice.actions;

export default cartSlice.reducer;