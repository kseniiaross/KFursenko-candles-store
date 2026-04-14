import { configureStore } from "@reduxjs/toolkit"
import authReducer from "./authSlice"
import cartReducer from "./cartSlice"
import modalReducer from "./modalSlice"
import lumiereReducer from "./lumiereSlice"

export const store = configureStore({

  reducer: {

    auth: authReducer,

    cart: cartReducer,

    modal: modalReducer,

    lumiere: lumiereReducer,

  },

})

export type RootState = ReturnType<typeof store.getState>

export type AppDispatch = typeof store.dispatch