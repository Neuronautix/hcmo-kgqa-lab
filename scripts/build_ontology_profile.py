#!/usr/bin/env python3
"""Build the ontology profile, terms, and prefixes JSON artifacts.

Loads ``ontology/current/hcmo.owl``, builds a structured profile via
``app.ontology.profiler`` and writes three files into
``ontology/profiles/``:

    hcmo_profile.json   -- full profile (classes + properties + counts)
    hcmo_terms.json     -- flat list of terms (iri/label/type/comment)
    hcmo_prefixes.json  -- prefix map

Usage:
    python scripts/build_ontology_profile.py [--ontology PATH] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import die, get_settings, info


def _term_to_dict(term) -> dict:
    # OntologyTerm pydantic model -> JSON dict using the terms.json schema.
    iri = getattr(term, "iri", "")
    return {
        "iri": iri,
        "label": getattr(term, "label", None),
        "type": getattr(term, "term_type", None) or getattr(term, "type", "unknown"),
        "comment": getattr(term, "comment", None),
    }


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ontology", default=str(settings.ontology_path))
    parser.add_argument("--out-dir", default=str(settings.profiles_dir))
    args = parser.parse_args(argv)

    try:
        from app.ontology.loader import load_ontology, load_prefixes
        from app.ontology.profiler import build_profile, profile_to_terms
    except Exception as exc:  # noqa: BLE001
        die(f"Could not import ontology backend modules: {exc}")

    ont_path = Path(args.ontology)
    if not ont_path.exists():
        die(f"Ontology not found: {ont_path}")

    info(f"Loading ontology from {ont_path}")
    graph = load_ontology(ont_path)
    info(f"Loaded {len(graph)} triples")

    profile = build_profile(graph)
    terms = [_term_to_dict(t) for t in profile_to_terms(profile)]
    prefixes = load_prefixes()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "hcmo_profile.json").write_text(
        json.dumps(profile, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "hcmo_terms.json").write_text(
        json.dumps(terms, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "hcmo_prefixes.json").write_text(
        json.dumps(prefixes, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )

    info(
        f"Wrote profile ({profile['counts']['classes']} classes, "
        f"{len(terms)} terms) to {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
