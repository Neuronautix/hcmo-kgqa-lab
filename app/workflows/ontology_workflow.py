"""Workflow: load ontology, build profile, build term index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger
from app.ontology.loader import load_ontology
from app.ontology.profiler import build_profile, profile_to_terms
from app.ontology.term_index import TermIndex

logger = get_logger("workflows.ontology")


def build_ontology_assets(write: bool = False) -> Tuple[Dict[str, Any], TermIndex]:
    """Load the ontology, build its profile and a TermIndex.

    If ``write`` is True, persist the profile to ``hcmo_profile.json`` (used by
    scripts; safe no-op for the UI which passes ``write=False``).
    """
    graph = load_ontology()
    profile = build_profile(graph)
    terms = profile_to_terms(profile)
    index = TermIndex(terms)

    if write:
        out = Path(settings.profile_json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        logger.info("Wrote ontology profile to %s", out)

    return profile, index


def load_term_index(prefer_json: bool = True) -> TermIndex:
    """Load a TermIndex from JSON if present, else from the ontology."""
    if prefer_json and Path(settings.terms_json_path).exists():
        return TermIndex.load()
    _, index = build_ontology_assets(write=False)
    return index
