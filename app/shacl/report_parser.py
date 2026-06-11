"""Parse a pyshacl validation results graph into structured violations."""

from __future__ import annotations

from typing import Any, Dict, List

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF

SH = Namespace("http://www.w3.org/ns/shacl#")


def _val(graph: Graph, subj, pred):
    for o in graph.objects(subj, pred):
        return str(o)
    return None


def parse_validation_graph(results_graph: Graph) -> List[Dict[str, Any]]:
    """Return a list of violation dicts from a SHACL results graph.

    Each dict has: focusNode, resultPath, message, severity, sourceShape,
    sourceConstraintComponent, value.
    """
    violations: List[Dict[str, Any]] = []
    for result in results_graph.subjects(RDF.type, SH.ValidationResult):
        violations.append(
            {
                "focusNode": _val(results_graph, result, SH.focusNode),
                "resultPath": _val(results_graph, result, SH.resultPath),
                "message": _val(results_graph, result, SH.resultMessage),
                "severity": _val(results_graph, result, SH.resultSeverity),
                "sourceShape": _val(results_graph, result, SH.sourceShape),
                "sourceConstraintComponent": _val(
                    results_graph, result, SH.sourceConstraintComponent
                ),
                "value": _val(results_graph, result, SH.value),
            }
        )
    return violations
