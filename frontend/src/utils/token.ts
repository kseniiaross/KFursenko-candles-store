
const ACCESS_KEY = "access";
const REFRESH_KEY = "refresh";
const USER_KEY = "user";

const LEGACY_KEYS = ["token", "access_token"] as const;

const isBrowser =
  typeof window !== "undefined" && typeof localStorage !== "undefined";

function safeGet(key: string): string | null {
  if (!isBrowser) return null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string): void {
  if (!isBrowser) return;
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

function safeRemove(key: string): void {
  if (!isBrowser) return;
  try {
    localStorage.removeItem(key);
  } catch {
  }
}

export function notifyAuthChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("auth-changed"));
}

export function getAccessToken(): string | null {
  const t = safeGet(ACCESS_KEY);
  return t ? t.trim() : null;
}

export function setAccessToken(token: string): void {
  const t = String(token || "").trim();
  if (!t) return;

  safeSet(ACCESS_KEY, t);

  for (const k of LEGACY_KEYS) safeRemove(k);

  notifyAuthChanged();
}

export function removeAccessToken(): void {
  safeRemove(ACCESS_KEY);
  notifyAuthChanged();
}

export function getRefreshToken(): string | null {
  const t = safeGet(REFRESH_KEY);
  return t ? t.trim() : null;
}

export function setRefreshToken(token: string): void {
  const t = String(token || "").trim();
  if (!t) return;

  safeSet(REFRESH_KEY, t);
  notifyAuthChanged();
}

export function removeRefreshToken(): void {
  safeRemove(REFRESH_KEY);
  notifyAuthChanged();
}

export function clearTokens(): void {
  safeRemove(ACCESS_KEY);
  safeRemove(REFRESH_KEY);
  for (const k of LEGACY_KEYS) safeRemove(k);
}

export function clearAuthStorage(): void {
  clearTokens();
  safeRemove(USER_KEY);
  notifyAuthChanged();
}

export const AUTH_STORAGE_KEYS = {
  ACCESS_KEY,
  REFRESH_KEY,
  USER_KEY,
} as const;