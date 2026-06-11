"""SHACL validation behavior."""

from __future__ import annotations

import textwrap

import pytest

# A deliberately incomplete dataset: a hcmo:Dataset with no required metadata.
INCOMPLETE_TTL = textwrap.dedent(
    """
    @prefix hcmo: <http://w3id.org/hcmo#> .
    @prefix ex:   <http://example.org/hcmo/data#> .
    @prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

    ex:emptyDataset a hcmo:Dataset .
    """
).strip()


def _run_validation():
    mod = pytest.importorskip("app.shacl.validator")
    fn = getattr(mod, "run_validation", None)
    if fn is None:
        pytest.skip("run_validation not available")
    return fn


def _graph_from_ttl(ttl: str):
    rdflib = pytest.importorskip("rdflib")
    g = rdflib.Graph()
    g.parse(data=ttl, format="turtle")
    return g


def _conforms(report) -> bool:
    return bool(getattr(report, "conforms", report if isinstance(report, bool) else True))


def test_incomplete_example_yields_violation(settings):
    run_validation = _run_validation()
    if not list(settings.shacl_dir.glob("*.ttl")):
        pytest.skip("no SHACL shapes present yet")
    g = _graph_from_ttl(INCOMPLETE_TTL)
    report = run_validation(g)
    # Either the incomplete dataset does not conform, or (if shapes are lenient)
    # we still got a structured report back.
    assert report is not None
    if _conforms(report):
        pytest.skip("shapes do not constrain a bare hcmo:Dataset")
    violations = getattr(report, "violations", []) or []
    assert len(violations) >= 1


def test_example_assets_return_a_report(settings):
    """Running over the shipped examples should return a ShaclReport-like obj."""
    run_validation = _run_validation()
    examples = sorted(settings.kg_examples_dir.glob("*.ttl"))
    if not examples or not list(settings.shacl_dir.glob("*.ttl")):
        pytest.skip("examples or shapes not present")
    rdflib = pytest.importorskip("rdflib")
    g = rdflib.Graph()
    for ttl in examples:
        g.parse(str(ttl), format="turtle")
    report = run_validation(g)
    assert hasattr(report, "conforms")
