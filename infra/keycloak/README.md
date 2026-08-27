# Keycloak Realm as-Code

This directory contains the Keycloak realm configuration as JSON (`realm-export.json`), automatically imported when the Keycloak container starts.

## Quick Start

### 1. Start Keycloak with its database

```bash
docker compose up -d kc-postgres keycloak
```

Wait for both services to be healthy (check with `docker compose ps`).

### 2. Access Keycloak Admin Console

- URL: http://localhost:8080/admin
- Bootstrap credentials: `admin` / `admin`

The realm `harness` should be automatically imported. You'll see it in the realm selector dropdown (top-left).

## Realm Configuration Summary

**Realm name**: `harness`

- **Status**: Enabled
- **User registration**: Disabled (no self-signup)
- **Organizations**: Enabled (Keycloak 26 feature)
- **Realm role**: `operator` (for platform operators)

### Clients

1. **admin-ui** (Public, OIDC)
   - Protocol: OpenID Connect
   - Flow: Authorization Code + PKCE (S256)
   - Redirect URIs: `http://localhost:3000/*`
   - Web Origins: `http://localhost:3000`
   - Direct Access Grants: Disabled
   - Default scopes: `web-origins`, `profile`, `email`, `roles`, `acr`, `organizations`, `audience`

2. **backend** (Bearer-only)
   - Protocol: OpenID Connect
   - No authentication flows enabled
   - Used only as an audience for token verification (non-interactive)

## Creating the First Platform Operator

### Step 1: Create a user in Keycloak

1. Go to http://localhost:8080/admin/master/console/#/realms/harness/users
2. Click "Create new user"
3. Fill in:
   - Username: `operator1` (or your choice)
   - Email: `operator@example.com`
   - First name, Last name: optional
   - Email Verified: toggle ON
   - Enabled: toggle ON
4. Click "Create"

### Step 2: Set a temporary password

1. On the new user's page, go to the "Credentials" tab
2. Click "Set Password"
3. Enter a password (e.g., `TempPassword123!`)
4. Toggle "Temporary" OFF (so user doesn't have to change on first login)
5. Click "Set Password"

### Step 3: Assign realm role `operator`

1. On the user's page, go to the "Role mapping" tab
2. Click "Assign role"
3. Filter for realm roles and select `operator`
4. Click "Assign"

### Verify operator access

Log out and log back in with the operator account at http://localhost:8080/admin. You should see the realm `harness` and be able to manage it.

## Creating Organizations

### Step 1: Create an organization

1. In the `harness` realm, go to **Organizations** (left sidebar, under "Configure")
2. Click "Create"
3. Fill in:
   - Name: `acme-corp` (example tenant company)
   - Display name: `ACME Corporation`
4. Click "Create"

Note: The organization is now available for management. Organization ID is auto-generated.

### Step 2: Add a tenant admin to the organization

#### Option A: Add existing user to organization

1. Go to the organization's "Members" tab
2. Click "Add member"
3. Select an existing user (or create one first via Users menu)
4. For each member, assign a role within the organization:
   - **owner** — full permissions (manages members, agents, knowledge bases, API keys)
   - **admin** — all permissions except member management
5. Click "Add"

#### Option B: Create a user and add to organization

1. Create a new user via Users menu (see "Creating the First Platform Operator" section above)
2. Do NOT assign the realm role `operator`
3. Go to Organizations → `acme-corp` → Members → Add member
4. Select the new user and assign role (e.g., `owner` or `admin`)

## Access Token Claims

When a tenant admin (organization member) logs in via the **admin-ui** client using OIDC Authorization Code + PKCE flow, they receive an access token with the following claims:

### Standard OIDC Claims

```json
{
  "exp": 1234567890,
  "iat": 1234567890,
  "auth_time": 1234567890,
  "jti": "...",
  "iss": "http://localhost:8080/realms/harness",
  "sub": "user-uuid",
  "typ": "Bearer",
  "azp": "admin-ui",
  "sid": "session-id",
  "acr": "1",
  "name": "User Full Name",
  "preferred_username": "username",
  "given_name": "First",
  "family_name": "Last",
  "email": "user@example.com",
  "email_verified": true
}
```

### Custom Claims (Tenant & Organization Context)

**Organization claim** (added via `oidc-organization-membership-mapper`):

```json
{
  "organization": {
    "id": "organization-uuid",
    "name": "acme-corp",
    "realm": "harness"
  }
}
```

Note: This claim appears when the user is a member of at least one organization. If not a member of any organization, the claim may be absent or null depending on Keycloak version.

**Roles claim** (realm roles):

```json
{
  "realm_access": {
    "roles": ["operator"]  // if user has operator role
  }
}
```

**Audience claim** (added via `oidc-audience-mapper`):

```json
{
  "aud": ["backend", "admin-ui"]
}
```

### Complete Example Token Payload (decoded)

```json
{
  "exp": 1693150190,
  "iat": 1693146590,
  "auth_time": 1693146590,
  "jti": "abc123def456",
  "iss": "http://localhost:8080/realms/harness",
  "sub": "550e8400-e29b-41d4-a716-446655440000",
  "typ": "Bearer",
  "azp": "admin-ui",
  "sid": "session-xyz",
  "acr": "1",
  "name": "Alice Admin",
  "preferred_username": "alice",
  "given_name": "Alice",
  "family_name": "Admin",
  "email": "alice@acme.com",
  "email_verified": true,
  "organization": {
    "id": "org-550e8400",
    "name": "acme-corp",
    "realm": "harness"
  },
  "realm_access": {
    "roles": []
  },
  "aud": ["backend", "admin-ui"]
}
```

## Backend Token Verification

The **backend** application verifies access tokens by:

1. Fetching the JWKS endpoint at `http://localhost:8080/realms/harness/protocol/openid-connect/certs`
2. Verifying the token's signature using the public key from JWKS
3. Validating the `iss` (issuer), `exp` (expiration), and `aud` (audience) claims
4. Extracting the `organization` claim to determine which tenant the request belongs to
5. Extracting `realm_access.roles` to check if user has `operator` role (for operator-only endpoints)

No client secret is needed for token verification — it's stateless and public-key based.

## Organization Membership Mapper (Technical Details)

The organization membership claim is added via the **oidc-organization-membership-mapper** protocol mapper on the `organizations` client scope:

- **Mapper type**: `oidc-organization-membership-mapper` (built-in Keycloak 26+)
- **Claim name**: `organization` (mapped to access token)
- **Claim value**: JSON object with `id`, `name`, `realm` fields

If the mapper is missing or not working as expected, check:
1. The realm export (`realm-export.json`) is correctly loaded
2. The `organizations` client scope exists
3. The `admin-ui` client includes `organizations` in default scopes
4. The Keycloak container logs for import errors: `docker logs chatbot-keycloak`

### Fallback (if organization membership claim is missing)

If Keycloak version or configuration doesn't support `oidc-organization-membership-mapper`, an alternative is to use **Keycloak Groups** as a fallback:

1. Create groups matching organization names (e.g., group `acme-corp`)
2. Add users to those groups
3. Use `oidc-group-membership-mapper` to map groups to a token claim (e.g., claim name: `org_groups`)

This approach maps organization membership to token roles/groups instead of a dedicated `organization` claim.

## Troubleshooting

### Keycloak won't start

Check logs:
```bash
docker logs chatbot-keycloak
```

Common issues:
- `kc-postgres` not healthy: Check `docker logs chatbot-kc-postgres`
- Port 8080 already in use: Change port in `docker-compose.yml`
- Realm import failed: Validate `realm-export.json` JSON syntax

### Token missing organization claim

1. Verify user is a member of at least one organization (Orgs → Members tab)
2. Verify the `admin-ui` client includes `organizations` in default client scopes
3. Re-export realm from KC admin console and compare with `realm-export.json`

### Login redirects to 404

Ensure redirect URI in `admin-ui` client matches FE URL exactly. Default is `http://localhost:3000/*`.

## Cleanup (Development)

To remove test users/orgs:

```bash
# Log in to admin console, or use Admin API
curl -X DELETE http://localhost:8080/admin/realms/harness/users/{user-id} \
  -H "Authorization: Bearer $(ADMIN_TOKEN)"
```

To reset the entire Keycloak database:

```bash
docker compose down kc-postgres keycloak
docker volume rm chatbot-kc_postgres_data
docker compose up -d kc-postgres keycloak
```

The realm will be re-imported from `realm-export.json`.
