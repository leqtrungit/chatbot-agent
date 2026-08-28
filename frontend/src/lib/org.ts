import { getAccessToken, getUserOrganization, isOperator } from "@/lib/auth";

const ORG_ID_KEY = "resolved_org_id";

/**
 * Organization info needed for tenant endpoints
 */
export interface OrgContext {
  org_id: string;
  org_alias: string;
}

/**
 * Resolve org_id from backend using operator endpoint
 * LIMITATION: Backend does not yet provide a /v2/me endpoint for tenants to resolve their own org.
 * Currently this only works for operators who can list all orgs.
 * For regular tenants, we store org_id in localStorage as a workaround.
 */
export async function resolveOrgId(): Promise<string | null> {
  // Check localStorage cache first
  const cached = typeof localStorage !== "undefined" ? localStorage.getItem(ORG_ID_KEY) : null;
  if (cached) return cached;

  const orgAlias = getUserOrganization();
  if (!orgAlias) return null;

  // Try to resolve via operator endpoint (only works for operators)
  if (isOperator()) {
    try {
      const token = await getAccessToken();
      if (!token) return null;

      const response = await fetch(
        new URL(`${process.env.NEXT_PUBLIC_API_URL || ""}/v2/operator/orgs`),
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        interface OrgResponse {
          id: string;
          alias: string;
        }
        const orgs = (await response.json()) as OrgResponse[];
        const org = orgs.find((o) => o.alias === orgAlias);
        if (org) {
          if (typeof localStorage !== "undefined") {
            localStorage.setItem(ORG_ID_KEY, org.id);
          }
          return org.id;
        }
      }
    } catch {
      // Fall through to localStorage fallback
    }
  }

  // For non-operators: LIMITATION - backend needs /v2/me endpoint
  // For now, return null and let UI handle the error/workaround
  return null;
}

/**
 * Clear cached org_id (e.g., on logout)
 */
export function clearOrgCache(): void {
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(ORG_ID_KEY);
  }
}

/**
 * Manually set org_id (temporary workaround for tenants until backend provides /v2/me)
 */
export function setOrgId(orgId: string): void {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(ORG_ID_KEY, orgId);
  }
}

/**
 * Get cached org_id
 */
export function getCachedOrgId(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(ORG_ID_KEY);
}
