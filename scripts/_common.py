"""Shared helpers for the HCMO-KGQA scripts.

Repo-root aware and tolerant of a partially-built backend: app.* imports are
done defensively so a script fails with a clear message rather than a traceback.
"""

from __future__ import annotations

import sys
from pathlib import Path

# --- Make the repo root importable (so ``import app`` works) ---------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def get_settings():
    """Return the application Settings, or a minimal fallback."""
    try:
        from app.core.config import get_settings as _gs

        return _gs()
    except Exception:  # noqa: BLE001
        from app.core.config import settings  # type: ignore

        return settings


def info(msg: str) -> None:
    print(f"[hcmo] {msg}")


def warn(msg: str) -> None:
    print(f"[hcmo][warn] {msg}", file=sys.stderr)


def die(msg: str, code: int = 1) -> "None":
    print(f"[hcmo][error] {msg}", file=sys.stderr)
    raise SystemExit(code)
