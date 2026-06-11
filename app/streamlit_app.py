"""HCMO-KGQA Lab — Streamlit entrypoint / landing page.

Ontology-native KGQA demonstrator over a single RDF graph backend
(Apache Jena / Fuseki). This module renders the landing page: design
principle, architecture, live config summary and a Fuseki connectivity
check. All backend access is wrapped defensively so the UI still renders
when backend modules or Fuseki are unavailable.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="HCMO-KGQA Lab", layout="wide")


# --------------------------------------------------------------------------- #
# Resilient backend helpers
# --------------------------------------------------------------------------- #
def get_settings_safe():
    """Return a settings object or None, never raising."""
    try:
        from app.core.config import get_settings

        return get_settings()
    except Exception:
        try:
            from app.core.config import settings

            return settings
        except Exception as exc:  # pragma: no cover - import guard
            st.session_state["_settings_error"] = str(exc)
            return None


def fuseki_ask_check(settings):
    """Run a trivial ASK against Fuseki. Returns (ok, message)."""
    try:
        from app.kg.sparql_client import FusekiClient
    except Exception as exc:
        return False, f"FusekiClient import failed: {exc}"
    try:
        client = FusekiClient(settings)
        result = client.query("ASK { ?s ?p ?o }")
        return True, f"Connected. ASK returned: {getattr(result, 'raw', result)!r}"
    except Exception as exc:
        return False, f"Could not reach Fuseki: {exc}"


# --------------------------------------------------------------------------- #
# Shared session state
# --------------------------------------------------------------------------- #
settings = get_settings_safe()
st.session_state.setdefault("settings", settings)
if settings is not None:
    st.session_state.setdefault("provider", getattr(settings, "LLM_PROVIDER", "openai"))


# --------------------------------------------------------------------------- #
# Page body
# --------------------------------------------------------------------------- #
st.title("HCMO-KGQA Lab")
st.caption("Ontology-native Knowledge-Graph Question Answering for HCMO")

st.markdown(
    """
### Single-graph design principle

**Apache Jena / Fuseki is the one and only RDF graph backend.**
There is no Neo4j, no property graph, and no Cypher anywhere in this system.
Every piece of knowledge lives as RDF triples in a single Fuseki dataset and is
queried exclusively with **SPARQL**. The ontology (HCMO) is the schema; SHACL
shapes validate the data; and all question answering grounds its answers in
SPARQL results over that single graph.
"""
)

with st.expander("Architecture", expanded=True):
    st.markdown(
        """
```mermaid
flowchart TD
    Q[Natural-language question] --> INJ[Injection / safety filter]
    INJ --> INT[Intent detection]
    INT --> RET[Ontology term retrieval]
    RET --> SP[SPARQL build: template-first or LLM-generated]
    SP --> VAL[SPARQL safety validation]
    VAL --> EXEC[Execute on Fuseki via SPARQL]
    EXEC --> ANS[Grounded answer + caveats]

    subgraph Backend [Single RDF graph backend]
        FUSEKI[(Apache Jena / Fuseki)]
    end
    EXEC --- FUSEKI
    ONT[HCMO ontology] --> RET
    SHACL[SHACL shapes] --> FUSEKI
```
"""
    )

st.subheader("Current configuration")
if settings is None:
    st.error(
        "Could not load settings from app.core.config. "
        f"{st.session_state.get('_settings_error', '')}"
    )
else:
    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Fuseki**")
        st.write({
            "FUSEKI_BASE_URL": getattr(settings, "FUSEKI_BASE_URL", "?"),
            "FUSEKI_DATASET": getattr(settings, "FUSEKI_DATASET", "?"),
            "query_endpoint": getattr(settings, "query_endpoint", "?"),
        })
    with cols[1]:
        st.markdown("**LLM**")
        st.write({
            "LLM_PROVIDER": getattr(settings, "LLM_PROVIDER", "?"),
            "LLM_MODEL": getattr(settings, "LLM_MODEL", None) or "(provider default)",
        })

st.subheader("Fuseki connectivity")
if st.button("Check Fuseki connection", disabled=settings is None):
    ok, msg = fuseki_ask_check(settings)
    if ok:
        st.success(msg)
    else:
        st.warning(msg)

st.subheader("Navigation")
st.markdown(
    """
Use the sidebar to explore the lab:

- **Ontology Explorer** — browse HCMO classes & properties, search terms.
- **KG Loader** — merge example graphs and load them into Fuseki.
- **SHACL Validation** — validate a data graph against HCMO shapes.
- **KGQA Workflow** — the main demonstrator: ask a question, watch every step.
- **SPARQL Playground** — run read-only SPARQL directly.
- **Evaluation** — run the evaluation harness and compare modes.
"""
)
