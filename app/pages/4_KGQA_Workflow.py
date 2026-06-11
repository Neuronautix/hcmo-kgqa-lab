"""KGQA Workflow — the main HCMO-KGQA demonstrator.

Ask a natural-language question and watch every workflow step:
injection filter, intent detection, ontology-term retrieval, SPARQL build,
SPARQL safety validation, execution on Fuseki, result table, grounded answer
and caveats. Choose template-first (default) or generated-SPARQL mode.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="KGQA Workflow — HCMO-KGQA", layout="wide")
st.title("KGQA Workflow")
st.caption("Ask a question. Every step grounds in the single Fuseki RDF graph.")

_STATUS_ICON = {"ok": "✅", "success": "✅", "warn": "⚠️", "warning": "⚠️",
                "error": "❌", "skipped": "⏭️", "pending": "⏳"}


def run_workflow(question, mode, provider):
    """Dispatch to the template or generated workflow, name-resilient."""
    import importlib

    if mode.startswith("Template"):
        module_name = "app.workflows.template_kgqa_workflow"
        candidates = ("run_template_kgqa", "run_kgqa", "run")
    else:
        module_name = "app.workflows.generated_sparql_workflow"
        candidates = ("run_generated_kgqa", "run_kgqa", "run")

    mod = importlib.import_module(module_name)
    last = None
    for name in candidates:
        f = getattr(mod, name, None)
        if callable(f):
            try:
                return f(question, provider=provider), name
            except TypeError:
                try:
                    return f(question), name
                except Exception as exc:
                    last = exc
            except Exception as exc:
                last = exc
    raise AttributeError(
        f"{module_name}: none of {candidates} usable ({last}). "
        f"Available: {[n for n in dir(mod) if not n.startswith('_')]}"
    )


settings = st.session_state.get("settings")
default_provider = getattr(settings, "LLM_PROVIDER", "openai") if settings else "openai"

question = st.text_input(
    "Question",
    value="How many experiments are in each cohort?",
    placeholder="Ask a question about the HCMO knowledge graph",
)
mode = st.radio(
    "Mode",
    ["Template-first (default)", "Generated-SPARQL (experimental)"],
    horizontal=True,
)
provider = st.text_input("LLM provider override (optional)", value=str(default_provider))

if st.button("Run KGQA", type="primary") and question.strip():
    try:
        result, fname = run_workflow(question, mode, provider or None)
        st.caption(f"Ran via {fname}().")
    except Exception as exc:
        st.error(f"Workflow failed to run: {exc}")
        result = None

    if result is not None:
        steps = getattr(result, "steps", []) or []
        st.subheader("Workflow trace")
        for step in steps:
            name = getattr(step, "name", "step")
            status = getattr(step, "status", "pending")
            icon = _STATUS_ICON.get(status, "•")
            with st.expander(f"{icon} {name} — {status}", expanded=(status in ("error",))):
                detail = getattr(step, "detail", "")
                if detail:
                    st.write(detail)
                data = getattr(step, "data", None)
                if data is not None:
                    if isinstance(data, str):
                        st.code(data)
                    else:
                        st.write(data)

        # Structured highlights regardless of step granularity.
        st.subheader("SPARQL")
        sparql = getattr(result, "sparql", None)
        if sparql is not None and getattr(sparql, "text", ""):
            st.code(sparql.text, language="sparql")
            if getattr(sparql, "template_name", None):
                st.caption(f"Template: {sparql.template_name}")
        else:
            st.info("No SPARQL produced.")

        validation = getattr(result, "validation", None)
        if validation is not None:
            ok = getattr(validation, "ok", True)
            st.markdown(f"**SPARQL safety:** {'✅ ok' if ok else '❌ blocked'}")
            for issue in getattr(validation, "issues", []) or []:
                lvl = getattr(issue, "level", "info")
                st.write(f"- [{lvl}] {getattr(issue, 'message', issue)}")

        st.subheader("Query result")
        qr = getattr(result, "query_result", None)
        if qr is not None:
            rows = getattr(qr, "rows", []) or []
            st.caption(f"{getattr(qr, 'count', len(rows))} row(s)")
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.info("Query returned no rows.")
        else:
            st.info("No query result.")

        st.subheader("Grounded answer")
        ans = getattr(result, "answer", None)
        if ans is not None:
            grounded = getattr(ans, "grounded", False)
            st.markdown(("✅ Grounded" if grounded else "⚠️ Not fully grounded"))
            st.write(getattr(ans, "answer", "") or "(no answer)")
            cites = getattr(ans, "citations", []) or []
            if cites:
                st.caption("Citations: " + ", ".join(map(str, cites)))
            caveats = getattr(ans, "caveats", []) or []
            if caveats:
                st.subheader("Missing information / uncertainty")
                for c in caveats:
                    st.warning(c)
        else:
            st.info("No answer produced.")
