"""Pytest configuration for odoo_mcp_connector unit tests.

These tests run without a live Odoo instance. This conftest stubs out
`odoo` and `odoo.http` in sys.modules before any controller module is
imported, then loads the controllers package via importlib so that
relative imports (from .utils import ...) resolve correctly.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# 1. Stub odoo packages — must happen before any addon module is imported.
# ---------------------------------------------------------------------------

_odoo = types.ModuleType("odoo")
_odoo_http = types.ModuleType("odoo.http")
_mock_request = MagicMock(name="odoo_request")
_odoo_http.request = _mock_request
_odoo.http = _odoo_http

# odoo.exceptions — stub the exception classes used in addon code.
_odoo_exceptions = types.ModuleType("odoo.exceptions")
class AccessError(Exception): pass
class UserError(Exception): pass
class ValidationError(Exception): pass
_odoo_exceptions.AccessError = AccessError
_odoo_exceptions.UserError = UserError
_odoo_exceptions.ValidationError = ValidationError
_odoo.exceptions = _odoo_exceptions

# odoo.fields — stub used by activity_actions (fields.Date.today()).
_odoo_fields = types.ModuleType("odoo.fields")
class _StubDate:
    @staticmethod
    def today():
        import datetime as _dt
        return _dt.date.today().isoformat()
_odoo_fields.Date = _StubDate
_odoo.fields = _odoo_fields

sys.modules.setdefault("odoo", _odoo)
sys.modules.setdefault("odoo.http", _odoo_http)
sys.modules.setdefault("odoo.exceptions", _odoo_exceptions)
sys.modules.setdefault("odoo.fields", _odoo_fields)

# ---------------------------------------------------------------------------
# 2. Make odoo_mcp_connector importable as a top-level package from
#    odoo_addons/ without triggering the Odoo-dependent __init__.py chain.
#
#    We register bare namespace modules for the package and sub-package,
#    then load only the files the tests actually need (utils, project_actions).
# ---------------------------------------------------------------------------

ADDONS_DIR = Path(__file__).resolve().parents[2]   # -> odoo_addons/
CONTROLLERS_DIR = ADDONS_DIR / "odoo_mcp_connector" / "controllers"

# Register namespace stubs so relative imports have a package to resolve against.
for _pkg_name in (
    "odoo_mcp_connector",
    "odoo_mcp_connector.controllers",
    "odoo_mcp_connector.models",
):
    if _pkg_name not in sys.modules:
        _mod = types.ModuleType(_pkg_name)
        _mod.__path__ = []   # marks it as a package
        sys.modules[_pkg_name] = _mod


def _load(dotted_name: str, file_path: Path) -> types.ModuleType:
    """Load a single .py file into sys.modules under the given dotted name."""
    if dotted_name in sys.modules:
        return sys.modules[dotted_name]
    spec = importlib.util.spec_from_file_location(dotted_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = dotted_name.rpartition(".")[0]
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load utils first — project_actions and crm_actions depend on it.
_load("odoo_mcp_connector.controllers.utils", CONTROLLERS_DIR / "utils.py")
_load("odoo_mcp_connector.controllers.project_actions", CONTROLLERS_DIR / "project_actions.py")
_load("odoo_mcp_connector.controllers.crm_actions", CONTROLLERS_DIR / "crm_actions.py")
_load("odoo_mcp_connector.controllers.activity_actions", CONTROLLERS_DIR / "activity_actions.py")
_load("odoo_mcp_connector.controllers.partner_actions", CONTROLLERS_DIR / "partner_actions.py")
