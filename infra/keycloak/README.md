# Keycloak Realm & Seeding

This directory contains the Keycloak realm configuration and seed data for the chatbot-agent platform.

## Quick Start with Docker Compose

The entire stack (database, API, frontend, Keycloak, and seed data) is brought up with one command:

```bash
# Copy example config (adjust passwords if needed)
cp .env.example .env

# Bring up all services
docker compose up -d --build

# Wait for all services to be healthy (usually 30-60 seconds)
docker compose ps

# When all services show "healthy" or are running:
# - Admin UI: http://localhost:3000
# - API: http://localhost:8000
# - Keycloak Admin: http://localhost:8080/admin
```

## What Gets Seeded

The `kc-seed` service runs automatically after both Keycloak and the API are ready, creating:

### Users & Roles

1. **Operator Account** (platform administrator)
   - Username: `operator`
   - Password: `operator`
   - Realm Role: `operator`
   - Used to create and manage organizations and tenants

2. **Demo Tenant Admin**
   - Username: `admin@demo.local`
   - Password: `demo`
   - Role: Admin of the `demo` organization (auto-created)

### Organizations

- **Demo Organization** (slug: `demo`)
  - Display name: "Demo Corp"
  - Members: `admin@demo.local` (as admin)
  - This organization is ready to use immediately after seeding

## Logging In

### Admin UI (Frontend)

1. Go to http://localhost:3000
2. Click **Sign In**
3. Use either:
   - **Operator**: username `operator` / password `operator` → can create and manage organizations
   - **Tenant Admin**: username `admin@demo.local` / password `demo` → manages only the `demo` org

### Keycloak Admin Console

1. Go to http://localhost:8080/admin
2. Username: `admin`
3. Password: `admin`
4. The realm `harness` is automatically imported and visible in the realm selector (top-left)

## Architecture Notes

### Token Claims & Hostname Handling

When the browser fetches a token via OIDC, Keycloak returns a token with claim `iss` (issuer) set to the URL the browser used to reach it. The API backend must verify this `iss` claim against a configured value.

The docker-compose stack handles this correctly:

- **KEYCLOAK_ISSUER** (env): `http://localhost:8080/realms/harness`
  - The issuer value expected in tokens (matches browser's perspective)
  - Browser reaches Keycloak via `http://localhost:8080`

- **KEYCLOAK_JWKS_URL** (env): `http://keycloak:8080/realms/harness/protocol/openid-connect/certs`
  - Where the backend API fetches public keys to verify tokens
  - Uses `keycloak` (container-internal hostname) because the API runs in the same network

- **KC_HOSTNAME** (Keycloak env): `http://localhost:8080`
  - Tells Keycloak to set `iss` and redirect URIs relative to `http://localhost:8080`
  - Without this, Keycloak might use container's internal hostname, breaking token verification

**These MUST differ in host part** (localhost vs keycloak) — it's not a bug.

## Realm Configuration

**Realm Name**: `harness`

### Clients

1. **admin-ui** (Public OIDC)
   - Redirect URIs: `http://localhost:3000/*`
   - Web Origins: `http://localhost:3000`
   - Flow: Authorization Code + PKCE (S256)
   - Direct Access Grants: **Disabled** (no password grant)
   - Scopes: web-origins, profile, email, roles, acr, organizations, audience
   - Used by the frontend admin UI

2. **backend** (Bearer-only)
   - No interactive flows
   - Used only for token verification (audience check)

3. **seed-cli** (Public OIDC, Development Only)
   - Flow: Direct Access Grants (Resource Owner Password) enabled
   - Scopes: profile, email, roles, audience
   - Used **only** by the seed script for automated setup; do not use in production
   - This is a convenience for local development — never enable password grant on a production client

### Roles

- **operator**: Platform operators who create and manage organizations

### Organizations Feature

Keycloak 26+ organizations are enabled for multi-tenant support. An organization:
- Has a unique slug (e.g., `demo`)
- Has members with roles (owner, admin, member, etc.)
- Is referenced in tokens via the `organization` claim (when user is a member)

The `organization` claim includes:
```json
{
  "id": "org-uuid",
  "name": "demo",
  "realm": "harness"
}
```

## Seed Script Details

The seed script (`seed.sh`) is idempotent — it's safe to run multiple times:

1. Waits for Keycloak to be healthy (polls `/.well-known/openid-configuration`)
2. Authenticates as `admin` user (from `KC_BOOTSTRAP_ADMIN_USERNAME/PASSWORD`)
3. Creates users if they don't exist (checks by username)
4. Sets passwords for new users
5. Assigns realm roles
6. Waits for the API to be healthy
7. Gets an `operator` token via the `seed-cli` client (which has password grant enabled)
8. Calls `POST /v2/operator/orgs` to create the `demo` organization
9. Prints a summary of endpoints and credentials

If the script runs again (e.g., after restarting containers), it skips creation steps for users and orgs that already exist.

**Key fix**: The script uses the `seed-cli` client for obtaining the operator token, not `admin-ui`. This is because `admin-ui` is intentionally locked to Authorization Code + PKCE flow for security (no direct password grant). The `seed-cli` client is a public client with password grant enabled, but only for local development.

## Manual User/Org Management

To create additional users or organizations:

### Via Keycloak Admin Console

1. Go to http://localhost:8080/admin
2. Select realm `harness` (top-left dropdown)
3. Left sidebar → **Users** or **Organizations**
4. Click **Create**

### Via Backend API (Recommended)

For organizations, use the backend API to ensure both Keycloak and the database are kept in sync:

```bash
# Get an operator token (using seed-cli which allows password grant)
TOKEN=$(curl -s http://localhost:8080/realms/harness/protocol/openid-connect/token \
  -d "client_id=seed-cli&username=operator&password=operator&grant_type=password" \
  | jq -r .access_token)

# Create organization
curl -X POST http://localhost:8000/v2/operator/orgs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "acme-corp",
    "name": "ACME Corporation"
  }'
```

**Note**: The `seed-cli` client is designed for development and automated scripts. In production, use the web UI (Authorization Code + PKCE flow) to obtain tokens.

## Realm Import & Export

The Keycloak realm is defined in `realm-export.json` and automatically imported when the `keycloak` container starts (via `--import-realm` command).

To export the current realm configuration (e.g., after manual changes):

```bash
docker exec chatbot-keycloak /opt/keycloak/bin/kc.sh export \
  --realm harness \
  --file /tmp/realm-export.json

docker cp chatbot-keycloak:/tmp/realm-export.json ./infra/keycloak/realm-export.json
```

Then commit the updated `realm-export.json` to version control.

## Troubleshooting

### Seed script doesn't run or fails

Check logs:
```bash
docker logs chatbot-kc-seed
```

Common issues:
- Keycloak not healthy: `docker logs chatbot-keycloak`
- API not ready: `docker logs chatbot-api`
- Seed script permissions: `chmod +x ./infra/keycloak/seed.sh`

### Login fails or redirects to 404

1. Check Keycloak is running: `docker compose ps keycloak`
2. Verify `admin-ui` client has correct redirect URI: `http://localhost:3000/*`
3. Verify frontend can reach Keycloak: `curl http://localhost:8080` from browser console

### Token verification fails on API

1. Verify token claim `iss` matches `KEYCLOAK_ISSUER` env var
2. Check `KEYCLOAK_JWKS_URL` is reachable from API container: `docker exec chatbot-api curl http://keycloak:8080/realms/harness/protocol/openid-connect/certs`
3. Check API logs: `docker logs chatbot-api`

### "User already exists" errors when re-running seed

This is expected and harmless — the script skips creating users that already exist. To reset:

```bash
# Remove Keycloak database and re-import
docker compose down keycloak kc-seed
docker volume rm chatbot-agent_kc_postgres_data
docker compose up -d keycloak kc-seed
```

## Development Without Docker

To run the API and frontend locally (for active development):

```bash
# Backend API (from backend/)
uv sync
uv run uvicorn app.main:app --port 8000

# Frontend (from frontend/)
npm install
npm run dev

# Keycloak and databases must still run in docker (or be set up separately)
docker compose up -d postgres redis kc-postgres keycloak
```

Update `.env` for local hostnames:
```
DATABASE_URL=postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot
REDIS_URL=redis://localhost:6379/0
KEYCLOAK_ISSUER=http://localhost:8080/realms/harness
KEYCLOAK_JWKS_URL=http://localhost:8080/realms/harness/protocol/openid-connect/certs
```
