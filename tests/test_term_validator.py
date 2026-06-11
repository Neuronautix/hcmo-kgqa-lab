"""Ontology term validation guardrail."""

from __future__ import annotations

import pytest

KNOWN = "http://w3id.org/hcmo#Dataset"
KNOWN_QUERY = (
    "PREFIX hcmo: <http://w3id.org/hcmo#> "
    "SELECT ?d WHERE { ?d a hcmo:Dataset } LIMIT 5"
)
UNKNOWN_QUERY = (
    "PREFIX hcmo: <http://w3id.org/hcmo#> "
    "SELECT ?d WHERE { ?d a hcmo:NotARealClassXYZ } LIMIT 5"
)


def _term_validator():
    mod = pytest.importorskip("app.guardrails.term_validator")
    for name in ("validate_terms", "validate_sparql_terms", "check_terms", "validate"):
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    pytest.skip("no term-validation function found")


def _has_issue(result) -> bool:
    if isinstance(result, bool):
        return not result
    if isinstance(result, (list, tuple)) and result and not isinstance(result, str):
        # list of unknown terms / issues
        return len(result) > 0
    for attr in ("ok", "valid"):
        if hasattr(result, attr):
            return not bool(getattr(result, attr))
    for attr in ("issues", "unknown", "unknown_terms"):
        if hasattr(result, attr):
            return bool(getattr(result, attr))
    if isinstance(result, dict):
        return bool(result.get("issues") or result.get("unknown")) or not result.get("ok", True)
    return False


def test_unknown_term_flagged():
    validate = _term_validator()
    assert _has_issue(validate(UNKNOWN_QUERY)), "unknown hcmo term should be flagged"


def test_known_terms_pass():
    validate = _term_validator()
    assert not _has_issue(validate(KNOWN_QUERY)), "known hcmo terms should pass"
