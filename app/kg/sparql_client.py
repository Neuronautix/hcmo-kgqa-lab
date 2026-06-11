"""Thin Fuseki/SPARQL client built on ``requests``.

Import-safe: no connection is opened at import or construction time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from app.core.config import Settings, settings as _default_settings
from app.core.logging import get_logger
from app.core.models import QueryResult

logger = get_logger("kg.sparql_client")


class FusekiError(RuntimeError):
    """Raised when a Fuseki request fails (connection or HTTP error)."""


class FusekiClient:
    """Client for SPARQL query / update / ask against a Fuseki dataset."""

    def __init__(self, settings: Optional[Settings] = None, timeout: float = 30.0):
        self.settings = settings or _default_settings
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    @property
    def _auth(self):
        if self.settings.FUSEKI_USER:
            return (self.settings.FUSEKI_USER, self.settings.FUSEKI_PASSWORD)
        return None

    # ------------------------------------------------------------------ #
    def query(self, sparql: str) -> QueryResult:
        """Run a SELECT/ASK/CONSTRUCT query and parse JSON results."""
        try:
            resp = requests.post(
                self.settings.query_endpoint,
                data={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
                auth=self._auth,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise FusekiError(
                f"Could not reach Fuseki at {self.settings.query_endpoint}: {exc}"
            ) from exc
        if resp.status_code >= 400:
            raise FusekiError(
                f"SPARQL query failed ({resp.status_code}): {resp.text[:500]}"
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise FusekiError(f"Non-JSON response from Fuseki: {resp.text[:300]}") from exc
        return self._parse_select(payload)

    def ask(self, sparql: str) -> bool:
        """Run an ASK query and return the boolean answer."""
        result = self.query(sparql)
        if result.raw and isinstance(result.raw, dict) and "boolean" in result.raw:
            return bool(result.raw["boolean"])
        return result.count > 0

    def update(self, sparql: str) -> None:
        """Run a SPARQL UPDATE statement."""
        try:
            resp = requests.post(
                self.settings.update_endpoint,
                data={"update": sparql},
                auth=self._auth,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise FusekiError(
                f"Could not reach Fuseki update endpoint: {exc}"
            ) from exc
        if resp.status_code >= 400:
            raise FusekiError(
                f"SPARQL update failed ({resp.status_code}): {resp.text[:500]}"
            )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_select(payload: Dict[str, Any]) -> QueryResult:
        # ASK form
        if "boolean" in payload:
            b = bool(payload["boolean"])
            return QueryResult(
                columns=["boolean"],
                rows=[{"boolean": b}],
                count=1,
                raw=payload,
            )
        head = payload.get("head", {})
        columns: List[str] = list(head.get("vars", []))
        bindings = payload.get("results", {}).get("bindings", [])
        rows: List[Dict[str, Any]] = []
        for b in bindings:
            row: Dict[str, Any] = {}
            for var in columns:
                cell = b.get(var)
                row[var] = cell.get("value") if cell else None
            rows.append(row)
        return QueryResult(columns=columns, rows=rows, count=len(rows), raw=payload)

    # ------------------------------------------------------------------ #
    def ping(self) -> bool:
        """Best-effort check that the endpoint answers a trivial ASK."""
        try:
            return self.ask("ASK { ?s ?p ?o }")
        except FusekiError:
            return False
