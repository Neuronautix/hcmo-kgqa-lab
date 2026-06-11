"""Load TTL data into Fuseki via the Graph Store Protocol (GSP)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import requests
from rdflib import Graph

from app.core.config import Settings, settings as _default_settings
from app.core.logging import get_logger

logger = get_logger("kg.graph_loader")


def _auth(s: Settings):
    return (s.FUSEKI_USER, s.FUSEKI_PASSWORD) if s.FUSEKI_USER else None


def _post_turtle(
    data: str,
    graph_uri: Optional[str],
    settings: Settings,
    timeout: float = 60.0,
) -> None:
    params = {"graph": graph_uri} if graph_uri else {"default": ""}
    try:
        resp = requests.post(
            settings.gsp_endpoint,
            params=params,
            data=data.encode("utf-8"),
            headers={"Content-Type": "text/turtle"},
            auth=_auth(settings),
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach GSP endpoint {settings.gsp_endpoint}: {exc}") from exc
    if resp.status_code >= 400:
        raise RuntimeError(f"GSP upload failed ({resp.status_code}): {resp.text[:500]}")
    logger.info("Uploaded turtle to %s (graph=%s)", settings.gsp_endpoint, graph_uri or "default")


def upload_turtle(
    path: Union[str, Path],
    graph_uri: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> None:
    """Upload a Turtle file into Fuseki (named graph or default)."""
    s = settings or _default_settings
    text = Path(path).read_text(encoding="utf-8")
    _post_turtle(text, graph_uri, s)


def upload_graph(
    graph: Graph,
    graph_uri: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> None:
    """Serialize an rdflib Graph to Turtle and upload it into Fuseki."""
    s = settings or _default_settings
    text = graph.serialize(format="turtle")
    _post_turtle(text, graph_uri, s)
