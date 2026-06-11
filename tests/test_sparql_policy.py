"""Read-only SPARQL guardrail policy."""

from __future__ import annotations

import pytest

WRITE_QUERIES = [
    "INSERT DATA { <urn:a> <urn:b> <urn:c> }",
    "DELETE WHERE { ?s ?p ?o }",
    "DROP GRAPH <urn:g>",
    "LOAD <http://example.org/data.ttl>",
    "CLEAR ALL",
]

SELECT_QUERY = (
    "PREFIX hcmo: <http://w3id.org/hcmo#>\n"
    "SELECT ?d WHERE { ?d a hcmo:Dataset } LIMIT 10"
)


def _validate_fn():
    mod = pytest.importorskip("app.guardrails.sparql_policy")
    fn = getattr(mod, "validate_sparql", None)
    if fn is None:
        pytest.skip("validate_sparql not implemented yet")
    return fn


def _is_ok(result) -> bool:
    # validate_sparql returns (SparqlValidationResult, effective_query)
    if isinstance(result, tuple):
        result = result[0]
    if isinstance(result, bool):
        return result
    for attr in ("ok", "valid", "allowed", "conforms"):
        if hasattr(result, attr):
            return bool(getattr(result, attr))
    if isinstance(result, dict):
        return bool(result.get("ok", result.get("valid")))
    return bool(result)


def _effective_query(result):
    if isinstance(result, tuple) and len(result) > 1 and isinstance(result[1], str):
        return result[1]
    for attr in ("normalized", "query", "effective"):
        val = getattr(result, attr, None)
        if isinstance(val, str):
            return val
    return None


@pytest.mark.parametrize("q", WRITE_QUERIES)
def test_write_operations_rejected(q):
    validate = _validate_fn()
    assert not _is_ok(validate(q)), f"write query should be rejected: {q[:20]}"


def test_select_accepted():
    validate = _validate_fn()
    assert _is_ok(validate(SELECT_QUERY))


def test_limit_enforced_for_unbounded_select():
    """A SELECT without LIMIT should be flagged or auto-limited."""
    validate = _validate_fn()
    unbounded = (
        "PREFIX hcmo: <http://w3id.org/hcmo#>\n"
        "SELECT ?d WHERE { ?d a hcmo:Dataset }"
    )
    result = validate(unbounded)
    effective = _effective_query(result)
    if effective is not None:
        # The accepted/normalized query must carry a LIMIT.
        assert "LIMIT" in effective.upper()
    else:
        # No normalized form exposed: it must at least flag the issue.
        assert not _is_ok(result)
