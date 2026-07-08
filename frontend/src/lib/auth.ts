const COOKIE_NAME = "admin_auth";

/**
 * Reads a cookie value by name from document.cookie. Client-side only.
 */
function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  if (!match) return null;
  return decodeURIComponent(match.slice(name.length + 1));
}

export function getAuthToken(): string | null {
  return readCookie(COOKIE_NAME);
}

export function setAuthToken(base64Credentials: string) {
  if (typeof document === "undefined") return;
  // 7 day expiry, path=/ so middleware and all routes can read it.
  const maxAge = 60 * 60 * 24 * 7;
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(
    base64Credentials
  )}; path=/; max-age=${maxAge}; SameSite=Lax`;
}

export function clearAuthToken() {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax`;
}

export function encodeCredentials(username: string, password: string): string {
  return btoa(`${username}:${password}`);
}

export function getAuthHeader(): string | null {
  const token = getAuthToken();
  if (!token) return null;
  return `Basic ${token}`;
}

export const AUTH_COOKIE_NAME = COOKIE_NAME;
