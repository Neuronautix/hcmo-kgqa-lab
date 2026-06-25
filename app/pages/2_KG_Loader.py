"""KG Loader — merge example RDF graphs and load them into Fuseki.

Provides buttons to (1) merge the example graphs into kg/generated,
(2) load the merged graph into the single Fuseki dataset, and (3) run
example count queries (datasets / experiments / cohorts / metrics).
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="KG Loader — HCMO-KGQA", layout="wide")
st.title("KG Loader")
st.caption("Single RDF backend: everything is merged into one Fuseki dataset.")


def get_settings():
    try:
        from app.core.config import get_settings as _gs

        return _gs()
    except Exception:
        return st.session_state.get("settings")


def _call(module_name, candidates, *args, **kwargs):
    """Import a workflow module and call the first matching function name."""
    import importlib

    mod = importlib.import_module(module_name)
    for name in candidates:
        f = getattr(mod, name, None)
        if callable(f):
            return f(*args, **kwargs), name
    raise AttributeError(
        f"{module_name}: none of {candidates} found. "
        f"Available: {[n for n in dir(mod) if not n.startswith('_')]}"
    )


settings = get_settings()

st.subheader("1. Merge example graphs")
if st.button("Merge example graphs into kg/generated"):
    try:
        result, fname = _call(
            "app.workflows.kg_loading_workflow",
            ("merge_example_graphs", "merge_examples", "merge_graphs", "build_merged_graph"),
        )
        st.success(f"Merged via {fname}().")
        st.write(result)
    except Exception as exc:
        st.error(f"Merge failed: {exc}")

st.subheader("2. Load merged graph into Fuseki")
if st.button("Load merged graph into Fuseki"):
    try:
        from app.workflows.kg_loading_workflow import build_merged_kg, load_into_fuseki

        # Build the merged graph (examples + ontology schema), then upload it.
        # ``load_into_fuseki`` requires the graph, so it can't be called bare.
        graph = build_merged_kg(include_ontology=True, settings=settings)
        load_into_fuseki(graph, settings=settings)
        st.success(f"Loaded {len(graph)} triples into Fuseki.")
    except Exception as exc:
        st.error(f"Load failed: {exc}")

st.subheader("3. Example count queries")

COUNTS = {
    "Datasets": "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?t . FILTER(CONTAINS(LCASE(STR(?t)), \"dataset\")) }",
    "Experiments": "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?t . FILTER(CONTAINS(LCASE(STR(?t)), \"experiment\")) }",
    "Cohorts": "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?t . FILTER(CONTAINS(LCASE(STR(?t)), \"cohort\")) }",
    "Metrics": "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?t . FILTER(CONTAINS(LCASE(STR(?t)), \"metric\")) }",
}

if st.button("Run example count queries"):
    try:
        from app.kg.sparql_client import FusekiClient

        client = FusekiClient(settings)
    except Exception as exc:
        st.error(f"Could not create FusekiClient: {exc}")
        client = None

    if client is not None:
        cols = st.columns(len(COUNTS))
        for col, (label, sparql) in zip(cols, COUNTS.items()):
            try:
                res = client.query(sparql)
                rows = getattr(res, "rows", [])
                value = "?"
                if rows:
                    first = rows[0]
                    value = next(iter(first.values())) if isinstance(first, dict) else first
                col.metric(label, value)
            except Exception as exc:
                col.metric(label, "err")
                col.caption(str(exc)[:80])
