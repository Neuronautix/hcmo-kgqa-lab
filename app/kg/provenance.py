"""Provenance helpers for tracking the named graph a triple came from.

These are intentionally lightweight stubs: full provenance (PROV-O) is out of
scope for the demo, but named-graph tagging is enough to let the UI show where
asserted vs. inferred triples originate.
"""

from __future__ import annotations

from typing import Dict

# Conventional named-graph URIs used across the loading workflow.
ASSERTED_GRAPH = "http://example.org/hcmo/graph/asserted"
INFERRED_GRAPH = "http://example.org/hcmo/graph/inferred"
MERGED_GRAPH = "http://example.org/hcmo/graph/merged"


def graph_for_stage(stage: str) -> str:
    """Map a pipeline stage name to its conventional named-graph URI."""
    return {
        "asserted": ASSERTED_GRAPH,
        "inferred": INFERRED_GRAPH,
        "merged": MERGED_GRAPH,
    }.get(stage, MERGED_GRAPH)


def stage_for_graph(graph_uri: str) -> str:
    """Inverse of :func:`graph_for_stage` (best effort)."""
    mapping: Dict[str, str] = {
        ASSERTED_GRAPH: "asserted",
        INFERRED_GRAPH: "inferred",
        MERGED_GRAPH: "merged",
    }
    return mapping.get(graph_uri, "unknown")


def tag_source(record: dict, graph_uri: str) -> dict:
    """Attach a ``_source_graph`` key to a result record (non-mutating copy)."""
    out = dict(record)
    out["_source_graph"] = graph_uri
    return out
