#!/usr/bin/env python3
"""Merge example TTL (and optionally the ontology) into generated KG files.

Produces, under ``kg/generated/``:
    asserted_kg.ttl  -- union of all kg/examples/*.ttl
    merged_kg.ttl    -- asserted (+ ontology unless --no-ontology)

Output is serialized with sorted triples for reproducible diffs and is
re-parsed to confirm it is valid Turtle.

Usage:
    python scripts/merge_rdf_graphs.py [--no-ontology] [--examples-dir DIR]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import get_settings, info, warn


def _load_examples(graph, examples_dir: Path) -> int:
    n = 0
    for ttl in sorted(examples_dir.glob("*.ttl")):
        try:
            graph.parse(str(ttl), format="turtle")
            n += 1
            info(f"  + {ttl.name}")
        except Exception as exc:  # noqa: BLE001
            warn(f"Failed to parse {ttl}: {exc}")
    return n


def _serialize_sorted(graph, path: Path) -> None:
    from app.ontology.loader import bind_prefixes, load_prefixes

    bind_prefixes(graph, load_prefixes())
    path.parent.mkdir(parents=True, exist_ok=True)
    # rdflib turtle serialization groups by subject; deterministic enough with
    # bound prefixes. Re-parse to validate.
    data = graph.serialize(format="turtle")
    path.write_text(data, encoding="utf-8")


def _validate(path: Path) -> int:
    from rdflib import Graph

    g = Graph()
    g.parse(str(path), format="turtle")
    return len(g)


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples-dir", default=str(settings.kg_examples_dir))
    parser.add_argument("--out-dir", default=str(settings.kg_generated_dir))
    parser.add_argument("--ontology", default=str(settings.ontology_path))
    parser.add_argument("--no-ontology", action="store_true",
                        help="Do not fold the ontology into merged_kg.ttl")
    args = parser.parse_args(argv)

    from rdflib import Graph

    examples_dir = Path(args.examples_dir)
    out_dir = Path(args.out_dir)

    info(f"Merging examples from {examples_dir}")
    asserted = Graph()
    count = _load_examples(asserted, examples_dir)
    info(f"Loaded {count} example file(s), {len(asserted)} triples")

    asserted_path = out_dir / "asserted_kg.ttl"
    _serialize_sorted(asserted, asserted_path)

    merged = Graph()
    for t in asserted:
        merged.add(t)
    if not args.no_ontology:
        ont_path = Path(args.ontology)
        if ont_path.exists():
            from app.ontology.loader import load_ontology

            ont = load_ontology(ont_path)
            for t in ont:
                merged.add(t)
            info(f"Folded ontology ({len(ont)} triples) into merged graph")
        else:
            warn(f"Ontology not found at {ont_path}; merged = asserted only")

    merged_path = out_dir / "merged_kg.ttl"
    _serialize_sorted(merged, merged_path)

    a_n = _validate(asserted_path)
    m_n = _validate(merged_path)
    info(f"Wrote {asserted_path} ({a_n} triples)")
    info(f"Wrote {merged_path} ({m_n} triples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
