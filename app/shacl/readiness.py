"""VCG-readiness reporting built on the SHACL validator + parser."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Union

from rdflib import Graph

from app.shacl.validator import GraphOrPath, _as_graph, run_validation


def _local(iri: str | None) -> str:
    if not iri:
        return "unknown"
    for sep in ("#", "/"):
        if sep in iri:
            return iri.rsplit(sep, 1)[-1]
    return iri


def vcg_readiness_report(data_graph: GraphOrPath) -> Dict[str, Any]:
    """Summarise missing mandatory metadata per resource and per class.

    Runs SHACL validation, then aggregates violations by focus node and by
    the class of each focus node, producing UI-friendly counts.
    """
    graph: Graph = _as_graph(data_graph)
    report = run_validation(graph)

    per_resource: Dict[str, list] = {}
    for v in report.violations:
        node = v.get("focusNode") or "unknown"
        per_resource.setdefault(node, []).append(
            {
                "path": _local(v.get("resultPath")),
                "message": v.get("message"),
                "severity": _local(v.get("severity")),
            }
        )

    # Map focus nodes to their rdf:type local name for per-class aggregation.
    per_class: Counter = Counter()
    for node in per_resource:
        cls = "Resource"
        try:
            from rdflib import RDF, URIRef

            for t in graph.objects(URIRef(node), RDF.type):
                cls = _local(str(t))
                break
        except Exception:  # noqa: BLE001
            pass
        per_class[cls] += 1

    return {
        "conforms": report.conforms,
        "ready": report.conforms,
        "total_violations": len(report.violations),
        "non_ready_resources": len(per_resource),
        "per_class": dict(per_class),
        "per_resource": per_resource,
        "text": report.text,
    }
