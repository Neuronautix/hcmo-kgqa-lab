"""Build a structured profile of an ontology graph."""

from __future__ import annotations

from typing import Any, Dict, List

from rdflib import OWL, RDF, RDFS, Graph, URIRef
from rdflib.term import Literal

from app.core.models import OntologyTerm


def _label(graph: Graph, subject: URIRef) -> str | None:
    for o in graph.objects(subject, RDFS.label):
        if isinstance(o, Literal):
            return str(o)
    return None


def _comment(graph: Graph, subject: URIRef) -> str | None:
    for o in graph.objects(subject, RDFS.comment):
        if isinstance(o, Literal):
            return str(o)
    return None


def _local_name(iri: str) -> str:
    for sep in ("#", "/"):
        if sep in iri:
            return iri.rsplit(sep, 1)[-1]
    return iri


def _collect(graph: Graph, rdf_type: URIRef) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen = set()
    for s in graph.subjects(RDF.type, rdf_type):
        if not isinstance(s, URIRef) or str(s) in seen:
            continue
        seen.add(str(s))
        items.append(
            {
                "iri": str(s),
                "local_name": _local_name(str(s)),
                "label": _label(graph, s),
                "comment": _comment(graph, s),
            }
        )
    return sorted(items, key=lambda d: d["iri"])


def build_profile(graph: Graph) -> Dict[str, Any]:
    """Build a JSON-serializable profile of classes and properties."""
    classes = _collect(graph, OWL.Class)
    object_props = _collect(graph, OWL.ObjectProperty)
    datatype_props = _collect(graph, OWL.DatatypeProperty)

    # Augment object/datatype properties with domain/range info.
    def _enrich(props: List[Dict[str, Any]]) -> None:
        for p in props:
            subj = URIRef(p["iri"])
            dom = [str(o) for o in graph.objects(subj, RDFS.domain)]
            rng = [str(o) for o in graph.objects(subj, RDFS.range)]
            p["domain"] = dom
            p["range"] = rng

    _enrich(object_props)
    _enrich(datatype_props)

    return {
        "classes": classes,
        "object_properties": object_props,
        "datatype_properties": datatype_props,
        "counts": {
            "classes": len(classes),
            "object_properties": len(object_props),
            "datatype_properties": len(datatype_props),
            "triples": len(graph),
        },
    }


def profile_to_terms(profile: Dict[str, Any]) -> List[OntologyTerm]:
    """Flatten a profile dict into a list of OntologyTerm objects."""
    terms: List[OntologyTerm] = []
    mapping = [
        ("classes", "class"),
        ("object_properties", "object_property"),
        ("datatype_properties", "datatype_property"),
    ]
    for key, term_type in mapping:
        for item in profile.get(key, []):
            terms.append(
                OntologyTerm(
                    iri=item["iri"],
                    label=item.get("label") or item.get("local_name"),
                    term_type=term_type,
                    comment=item.get("comment"),
                )
            )
    return terms
