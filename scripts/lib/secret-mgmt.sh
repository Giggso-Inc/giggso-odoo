#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# scripts/lib/secret-mgmt.sh — CONNECTOR_SECRET lifecycle management
#
# Summary:
#   Provides generate_secret() and secret_source_label(). The installer
#   uses these to either preserve an existing CONNECTOR_SECRET from the
#   calling environment or generate a fresh one when none is supplied.
#
#   Preserving the existing secret was the manual hot-patch applied on
#   the EC2 box tonight: the installer regenerated a new secret even
#   though CONNECTOR_SECRET was already exported, causing a mismatch
#   with the Odoo system parameter and breaking all tool calls.
#
# Version: 1.0.0
# Sourced by: scripts/install_odoo_mcp.sh
# ─────────────────────────────────────────────────────────────────────

# ── _SECRET_FROM_ENV ──────────────────────────────────────────────────
# Capture whether CONNECTOR_SECRET arrived from the environment BEFORE
# generate_secret() potentially fills it in. Used by secret_source_label.
_SECRET_FROM_ENV=""
if [ -n "${CONNECTOR_SECRET:-}" ]; then
  _SECRET_FROM_ENV="yes"
fi

# ── generate_secret ───────────────────────────────────────────────────
# Bug 5 fix: if CONNECTOR_SECRET is already set and non-empty, do not
# regenerate. Previous code set CONNECTOR_SECRET="${CONNECTOR_SECRET:-}"
# at the top of the main script (making it always "defined but possibly
# empty") and then generated a new value in generate_secret() only when
# empty — that part was correct, but the _tracking_ of "came from env"
# was lost. This module makes the intent explicit.
generate_secret() {
  # Use the existing value if non-empty; otherwise generate a new one.
  if [ -n "${CONNECTOR_SECRET:-}" ]; then
    return  # preserve the caller-supplied secret
  fi
  if command -v openssl >/dev/null 2>&1; then
    CONNECTOR_SECRET="$(openssl rand -hex 32)"
  else
    # Fallback when openssl is absent (uncommon on OCI Linux).
    CONNECTOR_SECRET="$(date +%s | sha256sum | awk '{print $1}')"
  fi
}

# ── secret_source_label ───────────────────────────────────────────────
# Returns a human-readable note for the next-steps banner so the
# operator knows whether the printed secret is fresh or preserved.
secret_source_label() {
  if [ -n "$_SECRET_FROM_ENV" ]; then
    echo "(preserved from prior install — matches existing Odoo system parameter)"
  else
    echo "(newly generated — copy into Odoo system parameter now)"
  fi
}
