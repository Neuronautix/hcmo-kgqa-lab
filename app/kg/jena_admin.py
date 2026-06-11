"""Best-effort helpers for managing Fuseki datasets via the admin API."""

from __future__ import annotations

from typing import Optional

import requests

from app.core.config import Settings, settings as _default_settings
from app.core.logging import get_logger

logger = get_logger("kg.jena_admin")


def _auth(s: Settings):
    return (s.FUSEKI_USER, s.FUSEKI_PASSWORD) if s.FUSEKI_USER else None


def dataset_exists(settings: Optional[Settings] = None, dataset: Optional[str] = None) -> bool:
    """Return True if the dataset is registered in Fuseki."""
    s = settings or _default_settings
    name = dataset or s.FUSEKI_DATASET
    try:
        resp = requests.get(
            f"{s.FUSEKI_BASE_URL.rstrip('/')}/$/datasets/{name}",
            auth=_auth(s),
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException as exc:
        logger.warning("dataset_exists check failed: %s", exc)
        return False


def create_dataset(
    settings: Optional[Settings] = None,
    dataset: Optional[str] = None,
    db_type: str = "tdb2",
) -> bool:
    """Create a persistent dataset. Returns True on success/already-exists."""
    s = settings or _default_settings
    name = dataset or s.FUSEKI_DATASET
    if dataset_exists(s, name):
        return True
    try:
        resp = requests.post(
            f"{s.FUSEKI_BASE_URL.rstrip('/')}/$/datasets",
            params={"dbName": name, "dbType": db_type},
            auth=_auth(s),
            timeout=20,
        )
        ok = resp.status_code in (200, 201)
        if not ok:
            logger.warning("create_dataset failed (%s): %s", resp.status_code, resp.text[:200])
        return ok
    except requests.RequestException as exc:
        logger.warning("create_dataset error: %s", exc)
        return False


def clear_dataset(settings: Optional[Settings] = None, dataset: Optional[str] = None) -> bool:
    """Remove all triples (default + named graphs) via SPARQL UPDATE."""
    s = settings or _default_settings
    name = dataset or s.FUSEKI_DATASET
    endpoint = f"{s.FUSEKI_BASE_URL.rstrip('/')}/{name}/update"
    try:
        resp = requests.post(
            endpoint,
            data={"update": "CLEAR ALL"},
            auth=_auth(s),
            timeout=20,
        )
        return resp.status_code < 400
    except requests.RequestException as exc:
        logger.warning("clear_dataset error: %s", exc)
        return False
