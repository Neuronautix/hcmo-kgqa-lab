"""Jinja SPARQL templates render and parse as valid SPARQL."""

from __future__ import annotations

from pathlib import Path

import pytest

# Sample slot values broad enough to satisfy any template's placeholders.
SAMPLE_SLOTS = {
    "dataset_iri": "ex:dataset1",
    "class_iri": "hcmo:Dataset",
    "required_prop": "hcmo:title",
    "min_sample_size": 5,
    "experiment_a": "ex:expA",
    "experiment_b": "ex:expB",
    "system_name": "intellicage",
    "metric": "distance",
    "species": "mus musculus",
    "strain": "c57bl",
    "phrase": "sleep",
    "limit": 50,
}

PREFIXES = {
    "hcmo": "http://w3id.org/hcmo#",
    "ex": "http://example.org/hcmo/data#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


def _template_files(settings) -> list[Path]:
    return sorted(settings.sparql_templates_dir.glob("*.jinja.rq"))


def test_template_dir_exists(settings):
    files = _template_files(settings)
    if not files:
        pytest.skip("no Jinja templates present yet")
    assert files


@pytest.mark.parametrize("idx", range(8))
def test_each_template_renders_and_parses(settings, idx):
    jinja2 = pytest.importorskip("jinja2")
    rdflib = pytest.importorskip("rdflib")
    from rdflib.plugins.sparql import prepareQuery

    files = _template_files(settings)
    if idx >= len(files):
        pytest.skip("fewer templates than parametrized index")
    tmpl_path = files[idx]
    source = tmpl_path.read_text(encoding="utf-8")
    env = jinja2.Environment(undefined=jinja2.Undefined)
    rendered = env.from_string(source).render(**SAMPLE_SLOTS)

    # Ensure prefixes are declared (templates carry their own, but be safe).
    prepareQuery(rendered, initNs=PREFIXES)
