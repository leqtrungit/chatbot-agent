import { getAccessToken } from "@/lib/auth";

/**
 * User identity info from GET /v2/me endpoint
 */
export interface UserIdentity {
  kind: "operator" | "tenant";
  user_id: string;
  email?: string;
  role?: "admin" | "owner"; // Only for tenants
  org?: {
    id: string;
    name: string;
    slug: string;
    status: string;
  };
}

/**
 * Organization info needed for tenant endpoints
 */
export interface OrgContext {
  org_id: string;
  org_alias: string;
}

// Cache for user identity
let _cachedIdentity: UserIdentity | null = null;
let _identityFetchPromise: Promise<UserIdentity | null> | null = null;

/**
 * Fetch user identity from GET /v2/me endpoint
 */
async function fetchUserIdentity(): Promise<UserIdentity | null> {
  // Avoid concurrent fetch calls
  if (_identityFetchPromise) {
    return _identityFetchPromise;
  }

  _identityFetchPromise = (async () => {
    try {
      const token = await getAccessToken();
      if (!token) return null;

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
      const response = await fetch(`${apiUrl}/v2/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        return null;
      }

      const identity = (await response.json()) as UserIdentity;
      _cachedIdentity = identity;
      return identity;
    } catch {
      return null;
    } finally {
      _identityFetchPromise = null;
    }
  })();

  return _identityFetchPromise;
}

/**
 * Get cached user identity if available (without fetching)
 */
export function getCachedIdentity(): UserIdentity | null {
  return _cachedIdentity;
}

/**
 * Get user identity, fetching from /v2/me if not cached
 */
export async function getUserIdentity(): Promise<UserIdentity | null> {
  if (_cachedIdentity) {
    return _cachedIdentity;
  }
  return fetchUserIdentity();
}

/**
 * Resolve org_id for tenant users
 * Returns null if user is operator or org not found
 */
export async function resolveOrgId(): Promise<string | null> {
  const identity = await getUserIdentity();
  if (!identity || identity.kind !== "tenant" || !identity.org) {
    return null;
  }
  return identity.org.id;
}

/**
 * Check if current user is an operator
 */
export async function isOperator(): Promise<boolean> {
  const identity = await getUserIdentity();
  return identity ? identity.kind === "operator" : false;
}

/**
 * Check if current user is a tenant
 */
export async function isTenant(): Promise<boolean> {
  const identity = await getUserIdentity();
  return identity ? identity.kind === "tenant" : false;
}

/**
 * Clear cached identity (e.g., on logout)
 */
export function clearIdentityCache(): void {
  _cachedIdentity = null;
  _identityFetchPromise = null;
}

/**
 * Get operator message for users without tenant access
 */
export function getOperatorMessage(): string {
  return (
    "You are currently logged in with operator privileges. " +
    "The organization management pages are only available to organization members. " +
    "Please log in with a tenant account to access agent and knowledge base management."
  );
}
