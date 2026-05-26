#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# scripts/lib/identity-prompts.sh — OIDC identity-provider selection
#
# Summary:
#   Provides select_identity_defaults(), which sets IDENTITY_ISSUER and
#   IDENTITY_JWKS_URL by interactively prompting the operator to choose
#   a known provider (Google, Microsoft Entra, Okta, or custom OIDC).
#
#   The prompt is SKIPPED when IDENTITY_ISSUER, IDENTITY_AUDIENCE, or
#   IDENTITY_JWKS_URL are already defined in the calling environment
#   (even if set to the empty string). This allows non-interactive
#   deployments to pass empty values and bypass the menu entirely —
#   which was the manual hot-patch applied on the EC2 box tonight.
#
# Version: 1.0.0
# Sourced by: scripts/install_odoo_mcp.sh
# ─────────────────────────────────────────────────────────────────────

# ── select_identity_defaults ─────────────────────────────────────────
# Bug 4 fix: use ${VAR+x} to detect *defined* (even if empty) vars.
# Previously the check was `if [ -n "$IDENTITY_ISSUER" ]` which fired
# the menu whenever the operator exported IDENTITY_ISSUER="" explicitly,
# causing interactive prompts mid-automated-deploy on the EC2 box.
select_identity_defaults() {
  # If ANY of the three identity vars are defined (set in env, even to ""),
  # skip the interactive menu — the operator made a deliberate choice.
  if [ -n "${IDENTITY_ISSUER+x}" ] \
     || [ -n "${IDENTITY_AUDIENCE+x}" ] \
     || [ -n "${IDENTITY_JWKS_URL+x}" ]; then
    return
  fi

  echo "Identity provider:"
  echo "  1) Google Cloud / Google Workspace"
  echo "  2) Microsoft Entra ID"
  echo "  3) Okta"
  echo "  4) Custom OIDC (enter issuer + JWKS manually)"
  read -r -p "Select [1-4, default 1]: " provider
  provider="${provider:-1}"
  case "$provider" in
    1)
      IDENTITY_ISSUER="https://accounts.google.com"
      IDENTITY_JWKS_URL="https://www.googleapis.com/oauth2/v3/certs"
      ;;
    2)
      read -r -p "Microsoft tenant ID: " tenant_id
      IDENTITY_ISSUER="https://login.microsoftonline.com/${tenant_id}/v2.0"
      IDENTITY_JWKS_URL="https://login.microsoftonline.com/${tenant_id}/discovery/v2.0/keys"
      ;;
    3)
      read -r -p "Okta domain, e.g. https://yourcompany.okta.com: " okta_domain
      IDENTITY_ISSUER="${okta_domain%/}/oauth2/default"
      IDENTITY_JWKS_URL="${okta_domain%/}/oauth2/default/v1/keys"
      ;;
    *)
      # Custom OIDC — caller's prompt_if_empty will collect issuer + JWKS.
      ;;
  esac
}
