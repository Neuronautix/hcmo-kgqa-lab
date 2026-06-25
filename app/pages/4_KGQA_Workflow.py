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


_MODE_MAP = {
    "Auto (template → generated)": "auto",
    "Template-first": "template",
    "Generated-SPARQL (experimental)": "generated",
}


def _resolve_provider(name):
    """Resolve the provider-override name to an LLMProvider (NullProvider offline)."""
    from app.llm.provider import get_provider

    try:
        from app.core.config import get_settings

        s = get_settings()
    except Exception:
        s = st.session_state.get("settings")
    if name and s is not None:
        try:
            s = s.model_copy(update={"LLM_PROVIDER": name})
        except Exception:
            pass
    return get_provider(s)


def run_workflow(question, mode_label, provider_name):
    """Run the unified KGQA orchestrator in the chosen mode."""
    from app.workflows.kgqa_workflow import run_kgqa

    mode = _MODE_MAP.get(mode_label, "auto")
    provider = _resolve_provider(provider_name)
    return run_kgqa(question, provider=provider, mode=mode), f"run_kgqa(mode={mode})"


settings = st.session_state.get("settings")
default_provider = getattr(settings, "LLM_PROVIDER", "openai") if settings else "openai"

# Curated example questions (the requested one first), covering the competency
# questions the template-first pipeline supports.
_PICK_PROMPT = "— pick an example —"
EXAMPLE_QUESTIONS = [
    "How many experiments are in each cohort?",
    "Which datasets were produced using the DigiGait system?",
    "What behavioral metrics does the metabolic phenotyping experiment measure?",
    "Which experiments studied BALB/c mice?",
    "Which datasets are VCG-ready and which are missing required metadata?",
    "List all home cage systems and their vendors.",
    "What strains were used across the sleep monitoring experiments?",
]

if "kgqa_question" not in st.session_state:
    st.session_state["kgqa_question"] = EXAMPLE_QUESTIONS[0]


def _apply_example():
    choice = st.session_state.get("kgqa_example")
    if choice and choice != _PICK_PROMPT:
        st.session_state["kgqa_question"] = choice


st.selectbox(
    "Example questions",
    [_PICK_PROMPT] + EXAMPLE_QUESTIONS,
    key="kgqa_example",
    on_change=_apply_example,
    help="Pick one to fill the question box; you can still edit it freely.",
)
question = st.text_input(
    "Question",
    key="kgqa_question",
    placeholder="Ask a question about the HCMO knowledge graph",
)
mode = st.radio(
    "Mode",
    list(_MODE_MAP.keys()),
    horizontal=True,
    help="Auto runs the template path and falls back to LLM-generated SPARQL "
         "when no template fits or the result is empty (needs an LLM provider).",
)
provider = st.text_input("LLM provider override (optional)", value=str(default_provider))

if st.button("Run KGQA", type="primary") and question.strip():
    try:
        result, fname = run_workflow(question, mode, provider or None)
        st.caption(f"Ran via {fname}.")
    except Exception as exc:
        st.error(f"Workflow failed to run: {exc}")
        result = None

    if result is not None:
        steps = getattr(result, "steps", []) or []
        strategy = next((s for s in steps if getattr(s, "name", "") == "strategy"), None)
        if strategy is not None:
            st.info(f"**Strategy:** {getattr(strategy, 'detail', '')}")
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
