"""Load the HCMO ontology and prefix map."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Union

from rdflib import Graph

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("ontology.loader")

# Fallback prefix map (used if the prefixes JSON is absent).
DEFAULT_PREFIXES: Dict[str, str] = {
    "hcmo": "http://w3id.org/hcmo#",
    "ex": "http://example.org/hcmo/data#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "sh": "http://www.w3.org/ns/shacl#",
}


def _guess_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".ttl",):
        return "turtle"
    if suffix in (".owl", ".rdf", ".xml"):
        # HCMO ontology is authored in Turtle despite the .owl extension.
        return "turtle"
    if suffix in (".nt",):
        return "nt"
    if suffix in (".jsonld", ".json"):
        return "json-ld"
    return "turtle"


def load_ontology(path: Optional[Union[str, Path]] = None) -> Graph:
    """Load the ontology into an rdflib Graph.

    Tries the guessed format first, then falls back to Turtle/RDF-XML.
    """
    ont_path = Path(path) if path else Path(settings.ontology_path)
    if not ont_path.exists():
        raise FileNotFoundError(f"Ontology file not found: {ont_path}")

    graph = Graph()
    fmt = _guess_format(ont_path)
    try:
        graph.parse(str(ont_path), format=fmt)
    except Exception:  # noqa: BLE001 - fall back to alternative formats
        for alt in ("turtle", "xml", "nt"):
            if alt == fmt:
                continue
            try:
                graph = Graph()
                graph.parse(str(ont_path), format=alt)
                break
            except Exception:  # noqa: BLE001
                continue
        else:
            raise
    bind_prefixes(graph, load_prefixes())
    logger.info("Loaded ontology %s (%d triples)", ont_path, len(graph))
    return graph


def load_prefixes(path: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    """Load the prefix map from JSON, falling back to defaults."""
    pfx_path = Path(path) if path else Path(settings.prefixes_json_path)
    if pfx_path.exists():
        try:
            with open(pfx_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read prefixes %s: %s", pfx_path, exc)
    return dict(DEFAULT_PREFIXES)


def bind_prefixes(graph: Graph, prefixes: Optional[Dict[str, str]] = None) -> Graph:
    """Bind a prefix map onto a graph for nicer serialisation."""
    for pfx, uri in (prefixes or DEFAULT_PREFIXES).items():
        graph.bind(pfx, uri, replace=True)
    return graph


def prefix_header(prefixes: Optional[Dict[str, str]] = None) -> str:
    """Return SPARQL ``PREFIX`` declaration lines for the given prefix map."""
    prefixes = prefixes or load_prefixes()
    return "\n".join(f"PREFIX {p}: <{u}>" for p, u in prefixes.items())
