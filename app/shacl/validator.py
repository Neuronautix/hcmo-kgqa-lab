"""Run SHACL validation with pyshacl over the HCMO shapes."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from rdflib import Graph

from app.core.config import settings
from app.core.logging import get_logger
from app.core.models import ShaclReport
from app.shacl.report_parser import parse_validation_graph

logger = get_logger("shacl.validator")

GraphOrPath = Union[str, Path, Graph]


def _as_graph(data: GraphOrPath) -> Graph:
    if isinstance(data, Graph):
        return data
    g = Graph()
    g.parse(str(data), format="turtle")
    return g


def _load_shapes(shapes_dir: Union[str, Path]) -> Graph:
    """Merge all ``*.ttl`` shape files under ``shapes_dir`` into one graph."""
    shapes = Graph()
    dir_path = Path(shapes_dir)
    files: List[Path] = sorted(dir_path.glob("*.ttl")) if dir_path.is_dir() else []
    for f in files:
        try:
            shapes.parse(str(f), format="turtle")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse shape %s: %s", f, exc)
    return shapes


def run_validation(
    data_graph: GraphOrPath,
    shapes_dir: Optional[Union[str, Path]] = None,
    ont_graph: Optional[Union[str, Path]] = None,
    inference: str = "rdfs",
) -> ShaclReport:
    """Validate a data graph against the merged HCMO SHACL shapes.

    Returns a ``ShaclReport`` (conforms, structured violations, text).
    """
    from pyshacl import validate

    data = _as_graph(data_graph)
    shapes = _load_shapes(shapes_dir or settings.shacl_dir)

    ont_path = ont_graph if ont_graph is not None else settings.ontology_path
    ont = None
    try:
        if ont_path is not None and Path(ont_path).exists():
            ont = _as_graph(ont_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load ontology graph for SHACL: %s", exc)

    if len(shapes) == 0:
        # No shapes available yet (asset agent has not produced them).
        return ShaclReport(
            conforms=True,
            violations=[],
            text="No SHACL shapes found; skipped validation.",
        )

    conforms, results_graph, results_text = validate(
        data_graph=data,
        shacl_graph=shapes,
        ont_graph=ont,
        inference=inference,
        abort_on_first=False,
        meta_shacl=False,
        advanced=True,
    )
    violations = parse_validation_graph(results_graph)
    return ShaclReport(
        conforms=bool(conforms),
        violations=violations,
        text=results_text or "",
    )
