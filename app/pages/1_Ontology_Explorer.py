"""Ontology Explorer — browse and search HCMO ontology terms.

Loads the ontology profile / term index, shows class & property counts,
a keyword-searchable term table, and per-term details. Degrades gracefully
when backend modules are unavailable.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Ontology Explorer — HCMO-KGQA", layout="wide")
st.title("Ontology Explorer")


def load_index():
    """Load a TermIndex, trying the workflow first, then the index loader."""
    # Preferred: a dedicated ontology workflow.
    try:
        from app.workflows import ontology_workflow as owf

        for fn in ("load_ontology", "build_term_index", "load_term_index", "run"):
            f = getattr(owf, fn, None)
            if callable(f):
                obj = f()
                idx = getattr(obj, "term_index", obj)
                if idx is not None:
                    return idx, None
    except Exception as exc:
        last = exc
    else:
        last = None

    # Fallback: directly build a TermIndex.
    try:
        from app.ontology.term_index import TermIndex

        for fn in ("load", "from_json", "from_ontology"):
            f = getattr(TermIndex, fn, None)
            if callable(f):
                try:
                    return f(), None
                except Exception as exc:
                    last = exc
        return TermIndex(), None
    except Exception as exc:
        return None, exc or last


def get_retriever(index):
    try:
        from app.ontology.retriever import OntologyTermRetriever

        return OntologyTermRetriever(index)
    except Exception:
        return None


def term_to_row(t):
    return {
        "label": getattr(t, "label", None) or "",
        "type": getattr(t, "term_type", "unknown"),
        "iri": getattr(t, "iri", ""),
        "comment": (getattr(t, "comment", None) or "")[:200],
    }


index, err = load_index()
if index is None:
    st.error(f"Could not load the ontology term index: {err}")
    st.stop()

try:
    all_terms = list(index.all_terms())
except Exception as exc:
    st.error(f"Term index loaded but all_terms() failed: {exc}")
    st.stop()


def count_type(prefix):
    return sum(1 for t in all_terms if getattr(t, "term_type", "") == prefix)


c1, c2, c3, c4 = st.columns(4)
c1.metric("Total terms", len(all_terms))
c2.metric("Classes", count_type("class"))
c3.metric("Object properties", count_type("object_property"))
c4.metric("Datatype properties", count_type("datatype_property"))

st.subheader("Search terms")
query = st.text_input("Keyword search", value="", placeholder="e.g. cohort, experiment, metric")

if query.strip():
    retriever = get_retriever(index)
    results = None
    if retriever is not None:
        try:
            rt = retriever.retrieve(query, k=50)
            results = getattr(rt, "terms", rt)
        except Exception:
            results = None
    if results is None:
        try:
            results = index.search(query, k=50)
        except Exception as exc:
            st.warning(f"Search failed: {exc}")
            results = []
else:
    results = all_terms

rows = [term_to_row(t) for t in results]
st.caption(f"{len(rows)} term(s)")
st.dataframe(rows, use_container_width=True, hide_index=True)

st.subheader("Term details")
iris = [r["iri"] for r in rows if r["iri"]]
if iris:
    chosen = st.selectbox("Select a term IRI", iris)
    term = None
    try:
        term = index.by_iri(chosen)
    except Exception:
        term = next((t for t in results if getattr(t, "iri", "") == chosen), None)
    if term is not None:
        st.json({
            "iri": getattr(term, "iri", ""),
            "label": getattr(term, "label", None),
            "term_type": getattr(term, "term_type", "unknown"),
            "comment": getattr(term, "comment", None),
        })
else:
    st.info("No terms to detail for the current search.")
