"""Stdlib logging helper."""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = os.environ.get("HCMO_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root = logging.getLogger("hcmo")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger under the ``hcmo`` namespace."""
    _configure_root()
    if not name.startswith("hcmo"):
        name = f"hcmo.{name}"
    return logging.getLogger(name)
