import { createSlice } from "@reduxjs/toolkit"
import type { PayloadAction } from "@reduxjs/toolkit"
import type { Candle } from "../types/candle"

type ModalState = {
  isOpen: boolean
  candle: Candle | null
}

const initialState: ModalState = {
  isOpen: false,
  candle: null,
}

const modalSlice = createSlice({
  name: "modal",
  initialState,

  reducers: {

    openSizeModal: (state, action: PayloadAction<Candle>) => {
      state.isOpen = true
      state.candle = action.payload
    },

    closeSizeModal: (state) => {
      state.isOpen = false
      state.candle = null
    },

  },
})

export const { openSizeModal, closeSizeModal } = modalSlice.actions

export default modalSlice.reducer