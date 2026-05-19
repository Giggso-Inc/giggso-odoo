from __future__ import annotations

import pytest

from odoo_mcp.config import parse_port


def test_parse_port_accepts_valid_port():
    assert parse_port("8088") == 8088


def test_parse_port_rejects_non_integer():
    with pytest.raises(RuntimeError):
        parse_port("nope")


def test_parse_port_rejects_out_of_range():
    with pytest.raises(RuntimeError):
        parse_port("70000")
