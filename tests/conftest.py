"""Shared pytest fixtures and connectivity helpers.

All tests must run OFFLINE: no Fuseki, no LLM keys. Tests that genuinely need
those resources are skipped via the helpers here.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def fuseki_available() -> bool:
    try:
        from app.core.config import get_settings

        base = get_settings().FUSEKI_BASE_URL
    except Exception:  # noqa: BLE001
        base = "http://localhost:3030"
    parsed = urlparse(base)
    return _port_open(parsed.hostname or "localhost", parsed.port or 3030)


def llm_available() -> bool:
    import os

    return bool(os.environ.get("LLM_API_KEY"))


requires_fuseki = pytest.mark.skipif(
    not fuseki_available(), reason="Fuseki endpoint not reachable"
)
requires_llm = pytest.mark.skipif(
    not llm_available(), reason="No LLM_API_KEY in environment"
)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def settings():
    cfg = pytest.importorskip("app.core.config")
    return cfg.get_settings()
