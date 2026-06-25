"""Deductive-closure reasoning over an in-memory RDF graph.

A reusable inference hook for the KG-loading workflow. Prefers ``owlrl``
(OWL-RL, then RDFS semantics) when installed and falls back to a minimal RDFS
subclass-propagation pass so reasoning still works offline without extra
dependencies. All functions are import-safe and never require a network.
"""

from __future__ import annotations

from typing import Tuple

from rdflib import BNode, Graph, RDF, RDFS, URIRef

from app.core.logging import get_logger

logger = get_logger("kg.reasoner")


def _expand(graph: Graph, mode: str) -> str:
    """Apply a deductive closure to ``graph`` in place; return the mode used."""
    if mode in ("owlrl", "auto"):
        try:
            import owlrl

            owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(graph)
            return "owlrl-owl"
        except Exception as exc:  # noqa: BLE001
            if mode == "owlrl":
                raise
            logger.warning("owlrl unavailable (%s); falling back to RDFS", exc)
    # RDFS path: prefer owlrl's RDFS semantics, else a minimal built-in pass.
    try:
        import owlrl

        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(graph)
        return "owlrl-rdfs"
    except Exception:  # noqa: BLE001
        added = True
        while added:
            added = False
            for s, _, o in list(graph.triples((None, RDF.type, None))):
                for _, _, sup in graph.triples((o, RDFS.subClassOf, None)):
                    if (s, RDF.type, sup) not in graph:
                        graph.add((s, RDF.type, sup))
                        added = True
        return "rdflib-rdfs-min"


def _drop_invalid(graph: Graph) -> int:
    """Remove triples whose subject/predicate are not storable, return the count.

    OWL-RL's ``eq-ref`` rule entails reflexive ``owl:sameAs`` over *every* term
    in the graph, including literals (e.g. ``"0.1.0" owl:sameAs "0.1.0"``).
    A literal in subject position is invalid RDF and Jena/Fuseki rejects the
    upload, so drop any triple with a non-IRI/blank-node subject (and,
    defensively, any non-IRI predicate).
    """
    invalid = [
        t for t in graph
        if not (isinstance(t[0], (URIRef, BNode)) and isinstance(t[1], URIRef))
    ]
    for t in invalid:
        graph.remove(t)
    return len(invalid)


def materialize_inference(graph: Graph, mode: str = "auto") -> Tuple[Graph, Graph]:
    """Compute the deductive closure of ``graph`` without mutating it.

    Returns ``(closed, inferred)`` where ``closed`` is the original triples plus
    all entailed triples and ``inferred`` holds only the newly entailed ones.

    ``mode`` is one of ``"auto"`` (OWL-RL, then degrade to RDFS), ``"owlrl"``
    (require OWL-RL), or ``"rdfs"`` (RDFS semantics).
    """
    base = Graph()
    for t in graph:
        base.add(t)

    closed = Graph()
    for t in base:
        closed.add(t)
    mode_used = _expand(closed, mode)
    dropped = _drop_invalid(closed)
    if dropped:
        logger.info("Dropped %d entailed triple(s) with non-IRI subjects", dropped)

    inferred = Graph()
    for t in closed:
        if t not in base:
            inferred.add(t)
    logger.info("Reasoning mode %s entailed %d new triple(s)", mode_used, len(inferred))
    return closed, inferred


def apply_reasoning(graph: Graph, mode: str = "auto") -> Graph:
    """Return a new graph: ``graph`` expanded with its deductive closure."""
    closed, _ = materialize_inference(graph, mode)
    return closed
