"""Workflow: merge example graphs, write generated KG, load into Fuseki."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from rdflib import Graph

from app.core.config import Settings, settings as _default_settings
from app.core.logging import get_logger
from app.kg.graph_loader import upload_graph
from app.kg.jena_admin import create_dataset
from app.ontology.loader import bind_prefixes, load_ontology, load_prefixes

logger = get_logger("workflows.kg_loading")


def merge_example_graphs(settings: Optional[Settings] = None) -> Graph:
    """Merge every ``*.ttl`` under the KG examples dir into one graph."""
    s = settings or _default_settings
    merged = Graph()
    examples = Path(s.kg_examples_dir)
    files: List[Path] = sorted(examples.glob("*.ttl")) if examples.is_dir() else []
    for f in files:
        try:
            merged.parse(str(f), format="turtle")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse %s: %s", f, exc)
    bind_prefixes(merged, load_prefixes())
    logger.info("Merged %d example files into %d triples", len(files), len(merged))
    return merged


def write_asserted_kg(graph: Graph, settings: Optional[Settings] = None) -> Path:
    """Serialize the merged graph to ``kg/generated/asserted_kg.ttl``."""
    s = settings or _default_settings
    out_dir = Path(s.kg_generated_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "asserted_kg.ttl"
    out.write_text(graph.serialize(format="turtle"), encoding="utf-8")
    return out


def build_merged_kg(
    include_ontology: bool = True,
    settings: Optional[Settings] = None,
) -> Graph:
    """Produce the merged KG (examples + optionally ontology schema).

    The reasoning/inference hook is a placeholder: callers may post-process
    this graph with an external reasoner before loading.
    """
    s = settings or _default_settings
    graph = merge_example_graphs(s)
    if include_ontology:
        try:
            graph += load_ontology()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not merge ontology schema: %s", exc)
    return graph


def write_merged_kg(graph: Graph, settings: Optional[Settings] = None) -> Path:
    s = settings or _default_settings
    out_dir = Path(s.kg_generated_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "merged_kg.ttl"
    out.write_text(graph.serialize(format="turtle"), encoding="utf-8")
    return out


def load_into_fuseki(
    graph: Graph,
    graph_uri: Optional[str] = None,
    ensure_dataset: bool = True,
    settings: Optional[Settings] = None,
) -> None:
    """Upload a graph into Fuseki (creating the dataset if needed)."""
    s = settings or _default_settings
    if ensure_dataset:
        create_dataset(s)
    upload_graph(graph, graph_uri=graph_uri, settings=s)


def run_kg_loading(
    write_files: bool = True,
    load_fuseki: bool = True,
    settings: Optional[Settings] = None,
) -> dict:
    """End-to-end: merge -> write asserted/merged -> load into Fuseki."""
    s = settings or _default_settings
    asserted = merge_example_graphs(s)
    result = {"asserted_triples": len(asserted), "files_written": [], "loaded": False}
    if write_files:
        result["files_written"].append(str(write_asserted_kg(asserted, s)))
        merged = build_merged_kg(include_ontology=True, settings=s)
        result["files_written"].append(str(write_merged_kg(merged, s)))
        result["merged_triples"] = len(merged)
    if load_fuseki:
        load_into_fuseki(asserted, settings=s)
        result["loaded"] = True
    return result
