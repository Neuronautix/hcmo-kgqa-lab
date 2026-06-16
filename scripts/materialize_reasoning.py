#!/usr/bin/env python3
"""Materialize entailed triples over the asserted KG + ontology.

Uses ``owlrl`` (OWL-RL / RDFS closure) when installed, otherwise falls back to
rdflib's built-in RDFS semantics. Writes:

    kg/generated/inferred_kg.ttl  -- only the newly entailed triples
    kg/generated/merged_kg.ttl    -- asserted + inferred (regenerated)

Serialization is sorted/reproducible.

Usage:
    python scripts/materialize_reasoning.py [--mode owlrl|rdfs] [--asserted PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import get_settings, info, warn


def _expand(graph, mode: str) -> str:
    """Apply a deductive closure to ``graph`` in place. Returns mode used."""
    if mode in ("owlrl", "auto"):
        try:
            import owlrl

            owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(graph)
            return "owlrl-owl"
        except Exception as exc:  # noqa: BLE001
            if mode == "owlrl":
                raise
            warn(f"owlrl unavailable ({exc}); falling back to rdflib RDFS")
    # rdflib RDFS fallback.
    try:
        import owlrl

        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(graph)
        return "owlrl-rdfs"
    except Exception:  # noqa: BLE001
        from rdflib.plugins.sparql.processor import prepareQuery  # noqa: F401

        # Minimal RDFS subclass propagation as a last resort.
        from rdflib import RDF, RDFS

        added = True
        while added:
            added = False
            for s, _, o in list(graph.triples((None, RDF.type, None))):
                for _, _, sup in graph.triples((o, RDFS.subClassOf, None)):
                    if (s, RDF.type, sup) not in graph:
                        graph.add((s, RDF.type, sup))
                        added = True
        return "rdflib-rdfs-min"


def _serialize_sorted(graph, path: Path) -> None:
    from app.ontology.loader import bind_prefixes, load_prefixes

    bind_prefixes(graph, load_prefixes())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(graph.serialize(format="turtle"), encoding="utf-8")


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["owlrl", "rdfs", "auto"], default="auto")
    parser.add_argument("--asserted", default=None)
    parser.add_argument("--ontology", default=str(settings.ontology_path))
    parser.add_argument("--out-dir", default=str(settings.kg_generated_dir))
    args = parser.parse_args(argv)

    from rdflib import Graph

    out_dir = Path(args.out_dir)
    asserted_path = Path(args.asserted) if args.asserted else out_dir / "asserted_kg.ttl"
    if not asserted_path.exists():
        warn(f"{asserted_path} missing; run merge_rdf_graphs.py first")
        return 1

    base = Graph()
    base.parse(str(asserted_path), format="turtle")
    n_asserted = len(base)
    ont_path = Path(args.ontology)
    if ont_path.exists():
        from app.ontology.loader import load_ontology

        for t in load_ontology(ont_path):
            base.add(t)

    closed = Graph()
    for t in base:
        closed.add(t)
    mode_used = _expand(closed, args.mode)
    info(f"Reasoning mode: {mode_used}")

    # OWL-RL's eq-ref rule entails reflexive owl:sameAs over *every* term in the
    # graph, including literals (e.g. ``"0.1.0" owl:sameAs "0.1.0"``). Literals
    # in subject position are not valid RDF and Fuseki/Jena rejects the upload
    # with "Subject is not a URI or blank node". Drop any triple whose subject
    # is not an IRI/blank node (and, defensively, any non-IRI predicate).
    from rdflib import BNode, URIRef

    invalid = [
        t for t in closed
        if not (isinstance(t[0], (URIRef, BNode)) and isinstance(t[1], URIRef))
    ]
    for t in invalid:
        closed.remove(t)
    if invalid:
        info(f"Dropped {len(invalid)} entailed triple(s) with non-IRI subjects")

    # inferred = closure minus the pre-closure graph
    inferred = Graph()
    for t in closed:
        if t not in base:
            inferred.add(t)
    info(f"Entailed {len(inferred)} new triple(s)")

    _serialize_sorted(inferred, out_dir / "inferred_kg.ttl")

    merged = Graph()
    asserted_only = Graph()
    asserted_only.parse(str(asserted_path), format="turtle")
    for t in asserted_only:
        merged.add(t)
    for t in inferred:
        merged.add(t)
    _serialize_sorted(merged, out_dir / "merged_kg.ttl")

    info(f"asserted={n_asserted} inferred={len(inferred)} merged={len(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
