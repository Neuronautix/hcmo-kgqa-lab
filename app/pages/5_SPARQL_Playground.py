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
    """Apply the SPARQL policy guardrail. Returns (ok, message)."""
    try:
        from app.guardrails import sparql_policy as pol
    except Exception:
        # Fallback: simple keyword block for write operations.
        lowered = sparql.lower()
        for kw in ("insert", "delete", "drop", "clear", "load", "create"):
            if kw in lowered:
                return False, f"Blocked: '{kw}' is not allowed (read-only)."
        return True, "ok (built-in heuristic; guardrail module not found)"

    for name in ("is_read_only", "validate", "check", "enforce_read_only"):
        f = getattr(pol, name, None)
        if callable(f):
            try:
                res = f(sparql)
                if isinstance(res, tuple):
                    return res
                if isinstance(res, bool):
                    return res, ("ok" if res else "Blocked by guardrail.")
                ok = getattr(res, "ok", True)
                return ok, getattr(res, "message", "") or ("ok" if ok else "blocked")
            except Exception as exc:
                return False, f"Guardrail error: {exc}"
    return True, "ok (no guardrail function found)"


settings = get_settings()
sparql = st.text_area("SPARQL query", value=SAMPLE, height=220)

if st.button("Run query", type="primary"):
    ok, msg = check_read_only(sparql)
    if not ok:
        st.error(msg)
    else:
        if "ok" not in msg.lower() or "heuristic" in msg or "no guardrail" in msg:
            st.caption(msg)
        try:
            from app.kg.sparql_client import FusekiClient

            client = FusekiClient(settings)
            result = client.query(sparql)
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
