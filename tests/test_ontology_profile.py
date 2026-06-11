"""Ontology loading + profile/terms building."""

from __future__ import annotations

import json

import pytest

CORE_CLASSES = {
    "http://w3id.org/hcmo#Dataset",
    "http://w3id.org/hcmo#HomeCageExperiment",
    "http://w3id.org/hcmo#AnimalCohort",
    "http://w3id.org/hcmo#HomeCageSystem",
    "http://w3id.org/hcmo#BehavioralMetric",
}


def test_ontology_parses_with_rdflib(settings):
    rdflib = pytest.importorskip("rdflib")
    path = settings.ontology_path
    if not path.exists():
        pytest.skip(f"ontology asset missing: {path}")
    g = rdflib.Graph()
    g.parse(str(path), format="turtle")
    assert len(g) > 0


def test_profile_builder_yields_core_classes(settings):
    loader = pytest.importorskip("app.ontology.loader")
    profiler = pytest.importorskip("app.ontology.profiler")
    if not settings.ontology_path.exists():
        pytest.skip("ontology asset missing")

    graph = loader.load_ontology()
    profile = profiler.build_profile(graph)
    class_iris = {c["iri"] for c in profile.get("classes", [])}
    missing = CORE_CLASSES - class_iris
    assert not missing, f"profile missing core classes: {missing}"


def test_terms_json_contains_five_core_classes(settings):
    terms_path = settings.terms_json_path
    if not terms_path.exists():
        pytest.skip(f"terms JSON not yet built: {terms_path}")
    data = json.loads(terms_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("terms", []) or [
            *data.get("classes", []),
        ]
    iris = {t.get("iri") for t in data if isinstance(t, dict)}
    missing = CORE_CLASSES - iris
    assert not missing, f"terms JSON missing core classes: {missing}"


def test_term_index_search(settings):
    ti_mod = pytest.importorskip("app.ontology.term_index")
    TermIndex = getattr(ti_mod, "TermIndex", None)
    if TermIndex is None:
        pytest.skip("TermIndex not available")
    if not settings.terms_json_path.exists() and not settings.ontology_path.exists():
        pytest.skip("no terms source available")
    idx = TermIndex.load()
    assert len(idx) >= 5
    hits = idx.search("metric")
    assert any("Metric" in (t.iri or "") for t in hits)
