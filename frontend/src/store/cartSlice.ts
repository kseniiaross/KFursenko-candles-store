import { createSlice } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";

export type CartLine = {
  variant_id: number;
  candle_id: number;

  name?: string;

  price: number;

  image?: string;

  size?: string;

  quantity: number;
};

type CartState = {
  items: CartLine[];
};

const initialState: CartState = {
  items: [],
};

/*
Find item by variant
Variant = unique candle size
*/
function findIndex(items: CartLine[], variant_id: number) {
  return items.findIndex((x) => x.variant_id === variant_id);
}

const cartSlice = createSlice({
  name: "cart",
  initialState,

  reducers: {

    /*
    Replace cart completely
    */
    setCart: (state, action: PayloadAction<CartLine[]>) => {
      state.items = action.payload ?? [];
    },

    /*
    Add candle variant
    */
    addToCart: (state, action: PayloadAction<CartLine>) => {

      const { variant_id } = action.payload;

      const idx = findIndex(state.items, variant_id);

      const qty = action.payload.quantity ?? 1;

      if (idx === -1) {

        state.items.push({
          ...action.payload,
          quantity: qty,
        });

      } else {

        state.items[idx].quantity += qty;

      }

    },

    /*
    Update quantity
    */
    updateQty: (
      state,
      action: PayloadAction<{
        variant_id: number;
        quantity: number;
      }>
    ) => {

      const idx = findIndex(state.items, action.payload.variant_id);

      if (idx !== -1) {

        const qty = Math.max(1, action.payload.quantity);

        state.items[idx].quantity = qty;

      }

    },

    /*
    Remove item
    */
    removeFromCart: (
      state,
      action: PayloadAction<{
        variant_id: number;
      }>
    ) => {

      state.items = state.items.filter(
        (x) => x.variant_id !== action.payload.variant_id
      );

    },

    /*
    Clear cart
    */
    clearCart: (state) => {
      state.items = [];
    },

  },
});

export const {
  setCart,
  addToCart,
  updateQty,
  removeFromCart,
  clearCart,
} = cartSlice.actions;

export default cartSlice.reducer;