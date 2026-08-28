#!/bin/bash

# Seed Keycloak realm with initial users and data for local development.
# Idempotent: safe to run multiple times. No-op if data already exists.

set -euo pipefail

KEYCLOAK_URL="${KEYCLOAK_URL:-http://keycloak:8080}"
API_URL="${API_URL:-http://api:8000}"
REALM="harness"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="admin"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# NOTE: these write to stderr (not stdout) deliberately. Several functions
# below are called as `VAR=$(some_function ...)`, returning their result by
# printing it as the last line of stdout; if log_* wrote to stdout too, that
# line would get captured into VAR along with the real return value and
# corrupt it (e.g. a user/org ID glued to a log message).
log_info() {
    echo -e "${GREEN}[seed]${NC} $*" >&2
}

log_warn() {
    echo -e "${YELLOW}[seed]${NC} $*" >&2
}

log_error() {
    echo -e "${RED}[seed]${NC} $*" >&2
}

# Wait for Keycloak to be ready (fetch well-known config)
wait_for_keycloak() {
    local max_retries=30
    local retry=0
    local well_known="${KEYCLOAK_URL}/realms/${REALM}/.well-known/openid-configuration"

    log_info "Waiting for Keycloak to be ready..."
    while [ $retry -lt $max_retries ]; do
        if curl -sf "$well_known" > /dev/null 2>&1; then
            log_info "Keycloak is ready."
            return 0
        fi
        retry=$((retry + 1))
        echo -n "."
        sleep 2
    done

    log_error "Keycloak did not become ready after ${max_retries} attempts."
    exit 1
}

# Get admin token from Keycloak master realm
get_admin_token() {
    local token_endpoint="${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    local response=$(curl -sf -X POST "$token_endpoint" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "client_id=admin-cli&username=${ADMIN_USERNAME}&password=${ADMIN_PASSWORD}&grant_type=password")

    echo "$response" | jq -r '.access_token'
}

# Create or get user in Keycloak
create_or_get_user() {
    local username=$1
    local email=$2
    local first_name=${3:-}
    local last_name=${4:-}
    local token=$5

    local admin_api="${KEYCLOAK_URL}/admin/realms/${REALM}/users"

    # Check if user already exists
    local existing=$(curl -sf "$admin_api?username=${username}" \
        -H "Authorization: Bearer ${token}" 2>/dev/null || echo "[]")

    if [ "$(echo "$existing" | jq 'length')" -gt 0 ]; then
        log_info "User '${username}' already exists, skipping creation."
        echo "$existing" | jq -r '.[0].id'
        return 0
    fi

    # Create new user
    local user_payload=$(cat <<EOF
{
    "username": "${username}",
    "email": "${email}",
    "firstName": "${first_name}",
    "lastName": "${last_name}",
    "enabled": true,
    "emailVerified": true
}
EOF
)

    local response=$(curl -s -i -X POST "$admin_api" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$user_payload" 2>/dev/null)

    local http_code=$(echo "$response" | head -1 | awk '{print $2}')
    local location=$(echo "$response" | grep -i "^location:" | head -1 | awk '{print $2}' | tr -d '\r')

    if [ "$http_code" = "201" ] && [ -n "$location" ]; then
        local user_id=$(basename "$location")
        log_info "Created user '${username}' (ID: ${user_id})."
        echo "$user_id"
        return 0
    else
        log_error "Failed to create user '${username}' (HTTP ${http_code})."
        return 1
    fi
}

# Set temporary password and make it permanent
set_user_password() {
    local user_id=$1
    local password=$2
    local token=$3

    local cred_endpoint="${KEYCLOAK_URL}/admin/realms/${REALM}/users/${user_id}/reset-password"
    local cred_payload=$(cat <<EOF
{
    "type": "password",
    "value": "${password}",
    "temporary": false
}
EOF
)

    curl -sf -X PUT "$cred_endpoint" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$cred_payload" > /dev/null 2>&1

    log_info "Set password for user ID ${user_id}."
}

# Assign realm role to user
assign_realm_role() {
    local user_id=$1
    local role_name=$2
    local token=$3

    local role_endpoint="${KEYCLOAK_URL}/admin/realms/${REALM}/roles/${role_name}"
    local role_response=$(curl -sf "$role_endpoint" \
        -H "Authorization: Bearer ${token}" 2>/dev/null)

    local role_id=$(echo "$role_response" | jq -r '.id // empty')

    if [ -z "$role_id" ]; then
        log_warn "Role '${role_name}' not found, skipping assignment."
        return 1
    fi

    # Check if user already has the role
    local user_roles="${KEYCLOAK_URL}/admin/realms/${REALM}/users/${user_id}/role-mappings/realm"
    local existing_roles=$(curl -sf "$user_roles" \
        -H "Authorization: Bearer ${token}" 2>/dev/null)

    if echo "$existing_roles" | jq -e --arg rn "$role_name" ".[] | select(.name == \$rn)" > /dev/null 2>&1; then
        log_info "User ${user_id} already has role '${role_name}', skipping."
        return 0
    fi

    # Assign role
    local role_payload=$(cat <<EOF
[{
    "id": "${role_id}",
    "name": "${role_name}",
    "composite": false,
    "clientRole": false,
    "containerId": "${REALM}"
}]
EOF
)

    curl -sf -X POST "$user_roles" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$role_payload" > /dev/null 2>&1

    log_info "Assigned realm role '${role_name}' to user ${user_id}."
}

# Wait for API to be ready (just check if port is open)
wait_for_api() {
    local max_retries=30
    local retry=0

    log_info "Waiting for API to be ready..."
    while [ $retry -lt $max_retries ]; do
        # Check health endpoint (no auth required); consider ready when server responds
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/health" 2>/dev/null)
        # API is ready if we got any HTTP response (not a connection error)
        if [ -n "$http_code" ] && echo "$http_code" | grep -qE '^[0-9]{3}$'; then
            log_info "API is ready (HTTP $http_code)."
            return 0
        fi
        retry=$((retry + 1))
        echo -n "."
        sleep 2
    done

    log_error "API did not become ready after ${max_retries} attempts."
    exit 1
}

# Create organization via API. Idempotent: if the org already exists, looks
# it up instead of re-creating it. Either way, prints the org's Keycloak
# Organization ID (OrgRead.keycloak_org_id) as the last line of stdout so
# callers can do `KC_ORG_ID=$(create_org_via_api ...)` — the caller needs
# this ID to add members to the Keycloak Organization afterwards.
create_org_via_api() {
    local org_slug=$1
    local org_name=$2
    local operator_username=$3
    local operator_password=$4

    # Get operator token via seed-cli (development client with password grant enabled)
    local token_endpoint="${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token"
    local token_response=$(curl -sf -X POST "$token_endpoint" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "client_id=seed-cli&username=${operator_username}&password=${operator_password}&grant_type=password" 2>/dev/null || echo '{}')

    local operator_token=$(echo "$token_response" | jq -r '.access_token // empty')

    if [ -z "$operator_token" ]; then
        log_error "Failed to get operator token for user '${operator_username}'."
        return 1
    fi

    # Check if org already exists; if so, read its Keycloak org ID off the
    # listing instead of re-creating (idempotent path).
    local orgs_endpoint="${API_URL}/v2/operator/orgs"
    local existing_orgs=$(curl -sf "$orgs_endpoint" \
        -H "Authorization: Bearer ${operator_token}" 2>/dev/null || echo '[]')

    local existing_kc_org_id=$(echo "$existing_orgs" | jq -r --arg slug "$org_slug" \
        '[.[] | select(.slug == $slug) | .keycloak_org_id // empty][0] // empty')

    if [ -n "$existing_kc_org_id" ]; then
        log_info "Organization '${org_slug}' already exists via API (Keycloak org ID: ${existing_kc_org_id}), skipping creation."
        echo "$existing_kc_org_id"
        return 0
    fi

    # Create organization
    local org_payload=$(cat <<EOF
{
    "slug": "${org_slug}",
    "name": "${org_name}"
}
EOF
)

    local create_response=$(curl -sf -X POST "$orgs_endpoint" \
        -H "Authorization: Bearer ${operator_token}" \
        -H "Content-Type: application/json" \
        -d "$org_payload" 2>/dev/null || echo '{}')

    local org_id=$(echo "$create_response" | jq -r '.id // empty')
    local kc_org_id=$(echo "$create_response" | jq -r '.keycloak_org_id // empty')

    if [ -z "$org_id" ] || [ -z "$kc_org_id" ]; then
        log_error "Failed to create organization '${org_slug}' via API. Response: ${create_response}"
        return 1
    fi

    log_info "Created organization '${org_slug}' via API (ID: ${org_id}, Keycloak org ID: ${kc_org_id})."
    echo "$kc_org_id"
    return 0
}

# Add an existing Keycloak user as a member of a Keycloak Organization.
#
# Endpoint verified against Keycloak 26.3 server source
# (services/src/main/java/org/keycloak/organization/admin/resource/OrganizationMemberResource.java,
# tag 26.3.0): POST /admin/realms/{realm}/organizations/{org-id}/members,
# Content-Type: application/json, body is the user's UUID as a JSON string.
# Returns 201 on success, 409 if the user is already a member of the
# organization (idempotent no-op for us), anything else is a real failure.
#
# This is the step that was completely missing before this fix: without it,
# the token minted for the tenant admin carries no `organization` claim
# (oidc-organization-membership-mapper only emits a claim for orgs the user
# actually belongs to), so every org-scoped route and GET /v2/me 403s.
add_org_member() {
    local kc_org_id=$1
    local user_id=$2
    local token=$3

    local members_endpoint="${KEYCLOAK_URL}/admin/realms/${REALM}/organizations/${kc_org_id}/members"

    local raw
    raw=$(curl -s -w '\n%{http_code}' -X POST "$members_endpoint" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "\"${user_id}\"" || echo -e "\n000")

    local http_code=$(echo "$raw" | tail -n1)
    local body=$(echo "$raw" | sed '$d')

    case "$http_code" in
        201)
            log_info "Added user (ID: ${user_id}) as a member of Keycloak Organization (ID: ${kc_org_id})."
            return 0
            ;;
        409)
            log_info "User (ID: ${user_id}) is already a member of Keycloak Organization (ID: ${kc_org_id}), skipping."
            return 0
            ;;
        *)
            log_error "Failed to add user (ID: ${user_id}) to Keycloak Organization (ID: ${kc_org_id}) (HTTP ${http_code}): ${body}"
            return 1
            ;;
    esac
}

# Print summary table
print_summary() {
    echo ""
    echo "=========================================="
    echo "Seed Complete - Platform is Ready"
    echo "=========================================="
    echo ""
    echo "Keycloak Admin Console:"
    echo "  URL:      http://localhost:8080/admin"
    echo "  Username: admin"
    echo "  Password: admin"
    echo ""
    echo "Demo Organization (demo):"
    echo "  Operator account:"
    echo "    Username: operator"
    echo "    Password: operator"
    echo "  Tenant admin account:"
    echo "    Username: admin@demo.local"
    echo "    Password: demo"
    echo ""
    echo "Admin UI:"
    echo "  URL: http://localhost:3000"
    echo "  Login with operator account above"
    echo ""
    echo "API:"
    echo "  Base URL: http://localhost:8000"
    echo ""
    echo "=========================================="
}

# Main flow
main() {
    log_info "Starting Keycloak seed..."

    wait_for_keycloak

    log_info "Authenticating as admin..."
    ADMIN_TOKEN=$(get_admin_token)

    if [ -z "$ADMIN_TOKEN" ]; then
        log_error "Failed to get admin token."
        exit 1
    fi

    log_info "Setting up initial users..."

    # Create operator user
    OPERATOR_ID=$(create_or_get_user "operator" "operator@harness.local" "Operator" "User" "$ADMIN_TOKEN")
    set_user_password "$OPERATOR_ID" "operator" "$ADMIN_TOKEN"
    assign_realm_role "$OPERATOR_ID" "operator" "$ADMIN_TOKEN"

    # Create demo org admin
    ADMIN_ID=$(create_or_get_user "admin@demo.local" "admin@demo.local" "Admin" "Demo" "$ADMIN_TOKEN")
    set_user_password "$ADMIN_ID" "demo" "$ADMIN_TOKEN"

    log_info "Setting up organization via API..."
    wait_for_api
    DEMO_KC_ORG_ID=$(create_org_via_api "demo" "Demo Corp" "operator" "operator")

    log_info "Adding tenant admin to the demo Keycloak Organization..."
    # Re-fetch the admin token rather than reusing the one from earlier in
    # this script: enough time has passed waiting on Keycloak/API readiness
    # that the original token may be close to (or past) its expiry.
    MEMBER_ADMIN_TOKEN=$(get_admin_token)
    if [ -z "$MEMBER_ADMIN_TOKEN" ]; then
        log_error "Failed to get admin token for organization membership call."
        exit 1
    fi
    add_org_member "$DEMO_KC_ORG_ID" "$ADMIN_ID" "$MEMBER_ADMIN_TOKEN"

    print_summary

    log_info "Seed completed successfully!"
}

main "$@"
