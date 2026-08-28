/**
 * OIDC Authorization Code + PKCE authentication for Keycloak
 */

const KEYCLOAK_URL = process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? "http://localhost:8080";
const KEYCLOAK_REALM = process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? "harness";
const KEYCLOAK_CLIENT_ID = process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? "admin-ui";

const TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";
const EXPIRES_AT_KEY = "expires_at";
const VERIFIER_KEY = "code_verifier";
const STATE_KEY = "oauth_state";

interface TokenPayload {
  organization?: string;
  realm_access?: {
    roles?: string[];
  };
  preferred_username?: string;
  email?: string;
  exp?: number;
}

/**
 * Generate a random string for PKCE code_verifier (43-128 chars)
 */
function generateCodeVerifier(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
  let verifier = "";
  for (let i = 0; i < 128; i++) {
    verifier += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return verifier;
}

/**
 * Base64url encode without padding
 */
function base64urlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

/**
 * Compute SHA-256 hash of verifier and base64url encode it
 */
async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return base64urlEncode(digest);
}

/**
 * Generate a random state parameter for CSRF protection
 */
function generateState(): string {
  return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
}

/**
 * Save PKCE and state to sessionStorage
 */
function saveAuthState(verifier: string, state: string): void {
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.setItem(VERIFIER_KEY, verifier);
    sessionStorage.setItem(STATE_KEY, state);
  }
}

/**
 * Retrieve and clear PKCE verifier from sessionStorage
 */
function getAndClearVerifier(): string | null {
  if (typeof sessionStorage === "undefined") return null;
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  return verifier;
}

/**
 * Retrieve and clear state from sessionStorage
 */
function getAndClearState(): string | null {
  if (typeof sessionStorage === "undefined") return null;
  const state = sessionStorage.getItem(STATE_KEY);
  sessionStorage.removeItem(STATE_KEY);
  return state;
}

/**
 * Save tokens to localStorage
 */
function saveTokens(accessToken: string, refreshToken: string, expiresIn: number): void {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    const expiresAt = Date.now() + expiresIn * 1000;
    localStorage.setItem(EXPIRES_AT_KEY, expiresAt.toString());
  }
}

/**
 * Clear all tokens from localStorage
 */
export function clearAllTokens(): void {
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(EXPIRES_AT_KEY);
  }
}

/**
 * Get stored access token
 */
function getStoredAccessToken(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Get stored refresh token
 */
function getStoredRefreshToken(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

/**
 * Get token expiration time
 */
function getTokenExpiresAt(): number | null {
  if (typeof localStorage === "undefined") return null;
  const expiresAt = localStorage.getItem(EXPIRES_AT_KEY);
  return expiresAt ? parseInt(expiresAt, 10) : null;
}

/**
 * Decode JWT payload (NO verification, only for reading claims)
 */
function decodeToken(token: string): TokenPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const decoded = atob(parts[1]);
    return JSON.parse(decoded) as TokenPayload;
  } catch {
    return null;
  }
}

/**
 * Initiate OIDC login flow
 */
export async function login(): Promise<void> {
  const verifier = generateCodeVerifier();
  const challenge = await generateCodeChallenge(verifier);
  const state = generateState();
  const redirectUri = `${window.location.origin}/callback`;

  saveAuthState(verifier, state);

  const params = new URLSearchParams({
    client_id: KEYCLOAK_CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "openid profile email",
    code_challenge: challenge,
    code_challenge_method: "S256",
    state,
  });

  window.location.href = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth?${params.toString()}`;
}

/**
 * Handle OAuth callback: exchange code for tokens
 */
export async function handleCallback(code: string, state: string): Promise<void> {
  const savedState = getAndClearState();
  const verifier = getAndClearVerifier();

  if (!savedState || savedState !== state) {
    throw new Error("State mismatch - possible CSRF attack");
  }

  if (!verifier) {
    throw new Error("Missing code verifier");
  }

  const redirectUri = `${window.location.origin}/callback`;

  const response = await fetch(
    `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: KEYCLOAK_CLIENT_ID,
        code,
        redirect_uri: redirectUri,
        code_verifier: verifier,
      }).toString(),
    }
  );

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Token exchange failed: ${error}`);
  }

  interface TokenResponse {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  }
  const data = (await response.json()) as TokenResponse;
  saveTokens(data.access_token, data.refresh_token, data.expires_in);
}

/**
 * Refresh access token using refresh token
 */
async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) return null;

  try {
    const response = await fetch(
      `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`,
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "refresh_token",
          client_id: KEYCLOAK_CLIENT_ID,
          refresh_token: refreshToken,
        }).toString(),
      }
    );

    if (!response.ok) {
      clearAllTokens();
      return null;
    }

    interface TokenResponse {
      access_token: string;
      refresh_token: string;
      expires_in: number;
    }
    const data = (await response.json()) as TokenResponse;
    saveTokens(data.access_token, data.refresh_token, data.expires_in);
    return data.access_token;
  } catch {
    clearAllTokens();
    return null;
  }
}

/**
 * Get valid access token, refresh if needed
 */
export async function getAccessToken(): Promise<string | null> {
  const token = getStoredAccessToken();
  if (!token) return null;

  const expiresAt = getTokenExpiresAt();
  if (!expiresAt) {
    clearAllTokens();
    return null;
  }

  const now = Date.now();
  const timeUntilExpiry = expiresAt - now;

  // Refresh if less than 30 seconds left
  if (timeUntilExpiry < 30000) {
    const refreshed = await refreshAccessToken();
    return refreshed;
  }

  return token;
}

/**
 * Log out: clear tokens and redirect to Keycloak logout
 */
export function logout(): void {
  clearAllTokens();

  const redirectUri = `${window.location.origin}/login`;
  const params = new URLSearchParams({
    post_logout_redirect_uri: redirectUri,
  });

  window.location.href = `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/logout?${params.toString()}`;
}

/**
 * Parse token claims
 */
export function parseToken(): TokenPayload | null {
  const token = getStoredAccessToken();
  if (!token) return null;
  return decodeToken(token);
}

/**
 * Check if user has operator role
 */
export function isOperator(): boolean {
  const payload = parseToken();
  if (!payload?.realm_access?.roles) return false;
  return payload.realm_access.roles.includes("operator");
}

/**
 * Check if user is logged in
 */
export function isLoggedIn(): boolean {
  const token = getStoredAccessToken();
  return !!token;
}

/**
 * Get current user organization (alias)
 */
export function getUserOrganization(): string | undefined {
  const payload = parseToken();
  return payload?.organization;
}
