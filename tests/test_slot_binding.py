"""Dataset slot binding makes dataset-scoped queries honest.

A question naming a specific dataset must filter the query to that dataset, so a
non-existent dataset yields zero rows (and an honest "no data" answer) instead
of silently returning every dataset's metrics. Runs offline against the example
RDF using rdflib directly — no Fuseki or LLM required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _slots(question):
    pytest.importorskip("pydantic")
    from app.core.models import RetrievedTerms
    from app.llm.slot_extractor import heuristic_slots

    return heuristic_slots(question, "metrics_for_experiment", RetrievedTerms())


def test_explicit_dataset_reference_binds_slot():
    assert _slots("What metrics for dataset ds_sleep2023?")["dataset"] == "ds_sleep2023"
    assert _slots("metrics for HCMO-DS-0003?")["dataset"].upper() == "HCMO-DS-0003"


def test_generic_dataset_mention_does_not_bind_slot():
    # A plain mention of "datasets" must NOT bind a dataset filter.
    assert "dataset" not in _slots("Which datasets are VCG-ready?")
    assert "dataset" not in _slots("List all datasets and their systems.")


def _example_graph():
    rdflib = pytest.importorskip("rdflib")
    g = rdflib.Graph()
    for f in sorted((REPO / "kg" / "examples").glob("*.ttl")):
        g.parse(str(f), format="turtle")
    return g


def _render_metrics(question):
    pytest.importorskip("jinja2")
    from jinja2 import Environment

    from app.workflows.templates import EMBEDDED_TEMPLATES

    tmpl = Environment().from_string(EMBEDDED_TEMPLATES["metrics_for_experiment"])
    return tmpl.render(**_slots(question)).strip()


def test_nonexistent_dataset_returns_no_rows():
    g = _example_graph()
    rows = list(g.query(_render_metrics("What metrics are measured for dataset ds_nope_9999?")))
    assert rows == []


def test_real_dataset_returns_rows():
    g = _example_graph()
    rows = list(g.query(_render_metrics("What metrics are measured for dataset ds_sleep2023?")))
    assert len(rows) >= 1


def test_unscoped_question_still_returns_rows():
    # No dataset slot -> broad query over all experiments (unchanged behavior).
    g = _example_graph()
    rows = list(g.query(_render_metrics("What behavioral metrics are measured?")))
    assert len(rows) >= 1
