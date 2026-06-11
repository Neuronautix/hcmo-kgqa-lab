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


def _discover_templates() -> list[Path]:
    # Collection-time discovery so we parametrize over real files only.
    try:
        from app.core.config import get_settings

        tdir = get_settings().sparql_templates_dir
    except Exception:  # noqa: BLE001
        tdir = Path(__file__).resolve().parents[1] / "sparql" / "templates"
    return sorted(Path(tdir).glob("*.jinja.rq"))


TEMPLATE_FILES = _discover_templates()


def test_template_dir_exists():
    if not TEMPLATE_FILES:
        pytest.skip("no Jinja templates present yet")
    assert TEMPLATE_FILES


@pytest.mark.skipif(not TEMPLATE_FILES, reason="no Jinja templates present yet")
@pytest.mark.parametrize(
    "tmpl_path",
    TEMPLATE_FILES or [None],
    ids=[p.name for p in TEMPLATE_FILES] or ["none"],
)
def test_each_template_renders_and_parses(tmpl_path):
    jinja2 = pytest.importorskip("jinja2")
    pytest.importorskip("rdflib")
    from rdflib.plugins.sparql import prepareQuery

    source = tmpl_path.read_text(encoding="utf-8")
    env = jinja2.Environment(undefined=jinja2.Undefined)
    rendered = env.from_string(source).render(**SAMPLE_SLOTS)

    # Ensure prefixes are declared (templates carry their own, but be safe).
    prepareQuery(rendered, initNs=PREFIXES)
