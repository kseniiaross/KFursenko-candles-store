// src/api/axiosInstance.ts
import axios, { AxiosHeaders } from "axios";
import type { InternalAxiosRequestConfig } from "axios";

import {
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  clearTokens,
} from "../utils/token";

/* ================================
   Base URL
================================ */

function normalizeApiBaseUrl(input: string): string {
  const trimmed = (input || "").trim();

  // If env var is missing, fallback to local dev
  if (!trimmed) return "http://127.0.0.1:8000/api";

  // If someone sets: kfursenko-...up.railway.app (without https://),
  // browsers treat it as a relative path on Vercel. Fix it.
  const withProtocol =
    /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;

  // Remove trailing slashes
  const normalized = withProtocol.replace(/\/+$/, "");

  // Ensure /api suffix exactly once
  return normalized.endsWith("/api") ? normalized : `${normalized}/api`;
}

const baseURL = normalizeApiBaseUrl(import.meta.env.VITE_API_URL ?? "");

// Note: we don't use withCredentials for JWT in headers
const api = axios.create({
  baseURL,
  withCredentials: false,
});

/* ================================
   Routes that DON'T require access token
================================ */

const NO_AUTH_ROUTES = [
  "/accounts/login/",
  "/accounts/token/",
  "/accounts/token/refresh/",
  "/accounts/register/",
] as const;

function isNoAuthRequest(config: InternalAxiosRequestConfig): boolean {
  const url = config.url ?? "";
  return NO_AUTH_ROUTES.some((route) => url.startsWith(route));
}

/* ================================
   Set Authorization header safely
================================ */

function setAuthHeader(config: InternalAxiosRequestConfig, token: string) {
  config.headers = AxiosHeaders.from(config.headers);
  config.headers.set("Authorization", `Bearer ${token}`);
}

/* ================================
   Request interceptor
================================ */

api.interceptors.request.use((config) => {
  if (isNoAuthRequest(config)) return config;

  const token = getAccessToken();
  if (token) setAuthHeader(config, token);

  return config;
});

/* ================================
   Refresh logic
================================ */

type RefreshResponse = {
  access: string;
};

let isRefreshing = false;
let queue: Array<(token: string | null) => void> = [];

function resolveQueue(token: string | null) {
  queue.forEach((cb) => cb(token));
  queue = [];
}

async function refreshAccessToken(): Promise<string> {
  const refresh = getRefreshToken();
  if (!refresh) throw new Error("No refresh token");

  // Use plain axios (not api) to avoid interceptor loops
  const response = await axios.post<RefreshResponse>(
    `${baseURL}/accounts/token/refresh/`,
    { refresh }
  );

  const newAccess = response.data?.access;
  if (!newAccess) throw new Error("Invalid refresh response");

  setAccessToken(newAccess);
  return newAccess;
}

/* ================================
   Response interceptor (401 -> refresh)
================================ */

api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    // Only handle axios errors
    if (!axios.isAxiosError(error)) {
      return Promise.reject(error);
    }

    const status = error.response?.status;
    const originalRequest = error.config;

    if (!originalRequest) {
      return Promise.reject(error);
    }

    // If it's not 401 OR it's an auth endpoint itself -> just reject
    if (status !== 401 || isNoAuthRequest(originalRequest as InternalAxiosRequestConfig)) {
      return Promise.reject(error);
    }

    const request = originalRequest as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Prevent infinite loops
    if (request._retry) {
      clearTokens();
      return Promise.reject(error);
    }

    request._retry = true;

    try {
      // If another refresh is already in progress, wait in queue
      if (isRefreshing) {
        return await new Promise((resolve, reject) => {
          queue.push((token) => {
            if (!token) {
              clearTokens();
              reject(error);
              return;
            }

            setAuthHeader(request, token);
            resolve(api(request));
          });
        });
      }

      isRefreshing = true;

      const newAccessToken = await refreshAccessToken();
      resolveQueue(newAccessToken);

      setAuthHeader(request, newAccessToken);
      return api(request);
    } catch (refreshError: unknown) {
      resolveQueue(null);
      clearTokens();
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export default api;