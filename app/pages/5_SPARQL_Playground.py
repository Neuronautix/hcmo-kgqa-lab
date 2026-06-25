"""SPARQL Playground — run read-only SPARQL against Fuseki.

Free SPARQL editor with the read-only guardrail applied (when the
guardrail module is available). Shows the result table and the raw JSON.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="SPARQL Playground — HCMO-KGQA", layout="wide")
st.title("SPARQL Playground")

SAMPLE = """SELECT ?s ?p ?o
WHERE { ?s ?p ?o }
LIMIT 25"""


def get_settings():
    try:
        from app.core.config import get_settings as _gs

        return _gs()
    except Exception:
        return st.session_state.get("settings")


def check_read_only(sparql):
    """Apply the read-only SPARQL guardrail.

    Returns ``(ok, message, effective_query)`` where ``effective_query`` is the
    policy-normalized query actually run (e.g. with an injected default LIMIT).
    """
    try:
        from app.guardrails.sparql_policy import validate_sparql
    except Exception:
        # Fallback: simple keyword block for write operations.
        lowered = (sparql or "").lower()
        for kw in ("insert", "delete", "drop", "clear", "load", "create"):
            if kw in lowered:
                return False, f"Blocked: '{kw}' is not allowed (read-only).", sparql
        return True, "ok (built-in heuristic; guardrail module not found)", sparql

    result, effective = validate_sparql(sparql)
    errors = [i.message for i in result.issues if i.level == "error"]
    infos = [i.message for i in result.issues if i.level == "info"]
    if not result.ok:
        return False, "Blocked by read-only guardrail: " + "; ".join(errors), sparql
    return True, ("; ".join(infos) if infos else "ok"), effective


settings = get_settings()
sparql = st.text_area("SPARQL query", value=SAMPLE, height=220)

if st.button("Run query", type="primary"):
    ok, msg, effective = check_read_only(sparql)
    if not ok:
        st.error(msg)
    else:
        if msg and msg != "ok":
            st.caption(msg)
        try:
            from app.kg.sparql_client import FusekiClient

            client = FusekiClient(settings)
            result = client.query(effective)
        except Exception as exc:
            st.error(f"Query failed: {exc}")
            result = None

        if result is not None:
            rows = getattr(result, "rows", []) or []
            cols = getattr(result, "columns", []) or []
            st.subheader("Results")
            st.caption(f"{getattr(result, 'count', len(rows))} row(s); columns: {cols}")
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.info("No rows returned (or ASK/boolean query).")

            st.subheader("Raw")
            raw = getattr(result, "raw", None)
            try:
                st.json(raw if raw is not None else {"columns": cols, "rows": rows})
            except Exception:
                st.code(str(raw))
