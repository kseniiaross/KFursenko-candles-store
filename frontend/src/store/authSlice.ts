import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { clearAuthStorage, getAccessToken, setAccessToken, setRefreshToken } from "../utils/token";
import type { AuthState, User } from "../types/auth";

type CredentialsPayload = {
  access: string;
  refresh?: string;
  user?: User | null;
};

const initialState: AuthState = {
  token: getAccessToken(),
  user: null,
  isLoggedIn: Boolean(getAccessToken()),
};

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    setCredentials: (state, action: PayloadAction<CredentialsPayload>) => {
      const access = String(action.payload.access || "").trim();
      const refresh = action.payload.refresh ? String(action.payload.refresh).trim() : "";

      if (!access) {
        state.token = null;
        state.user = null;
        state.isLoggedIn = false;
        clearAuthStorage();
        return;
      }

      state.token = access;
      state.user = action.payload.user ?? null;
      state.isLoggedIn = true;

      setAccessToken(access);
      if (refresh) setRefreshToken(refresh);
    },

    logout: (state) => {
      state.token = null;
      state.user = null;
      state.isLoggedIn = false;
      clearAuthStorage();
    },

    setUser: (state, action: PayloadAction<User | null>) => {
      state.user = action.payload;
    },
  },
});

export const { setCredentials, logout, setUser } = authSlice.actions;
export default authSlice.reducer;