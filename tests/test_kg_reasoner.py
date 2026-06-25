"""Deductive-closure reasoning hook.

Runs offline: the reasoner degrades to a minimal built-in RDFS pass when
``owlrl`` is not installed, so subclass entailment still works without any
optional dependency or network access.
"""

from __future__ import annotations

import pytest


def test_apply_reasoning_entails_subclass_types():
    pytest.importorskip("rdflib")
    from rdflib import Graph, RDF, RDFS, URIRef

    from app.kg.reasoner import apply_reasoning, materialize_inference

    EX = "http://example.org/"
    animal = URIRef(EX + "Animal")
    mouse = URIRef(EX + "Mouse")
    m1 = URIRef(EX + "m1")

    g = Graph()
    g.add((mouse, RDFS.subClassOf, animal))
    g.add((m1, RDF.type, mouse))

    closed = apply_reasoning(g, mode="auto")
    # m1 should now be typed as Animal via subclass entailment.
    assert (m1, RDF.type, animal) in closed
    # The input graph must not be mutated.
    assert (m1, RDF.type, animal) not in g

    _, inferred = materialize_inference(g, mode="auto")
    assert (m1, RDF.type, animal) in inferred
    # Inferred holds only new triples, not the asserted ones.
    assert (m1, RDF.type, mouse) not in inferred


def test_materialize_inference_empty_graph_does_not_raise():
    pytest.importorskip("rdflib")
    from rdflib import Graph

    from app.kg.reasoner import materialize_inference

    # An empty input must reason cleanly. OWL-RL contributes axiomatic schema
    # triples, so we don't assert emptiness — only that the closure is a
    # superset of the inferred triples and nothing blew up.
    closed, inferred = materialize_inference(Graph(), mode="auto")
    assert all(t in closed for t in inferred)


def test_build_merged_kg_reason_flag_runs_offline():
    pytest.importorskip("rdflib")
    pytest.importorskip("pydantic")
    from app.workflows.kg_loading_workflow import build_merged_kg

    # Reasoning over the merged graph must not raise and must return a graph.
    graph = build_merged_kg(include_ontology=False, reason=True)
    assert graph is not None
