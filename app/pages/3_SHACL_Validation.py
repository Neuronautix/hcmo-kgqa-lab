"""SHACL Validation — validate a data graph against HCMO shapes.

Pick a data graph (examples or generated/merged), run SHACL validation via
the shacl_workflow, and show conformance, violations, a VCG-readiness summary
and an optional LLM explanation.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="SHACL Validation — HCMO-KGQA", layout="wide")
st.title("SHACL Validation")


def get_settings():
    try:
        from app.core.config import get_settings as _gs

        return _gs()
    except Exception:
        return st.session_state.get("settings")


def run_shacl(graph_choice):
    """Validate the chosen data graph against the HCMO SHACL shapes.

    ``graph_choice`` is a UI label ("examples" / "generated/merged"), not a
    file path, so it must be resolved to an actual graph before validation.
    """
    from pathlib import Path

    from app.core.config import settings as cfg
    from app.shacl.validator import run_validation
    from app.workflows.kg_loading_workflow import build_merged_kg, merge_example_graphs

    if graph_choice == "examples":
        data_graph = merge_example_graphs(cfg)
    else:  # "generated/merged"
        merged_file = Path(cfg.kg_generated_dir) / "merged_kg.ttl"
        data_graph = (
            str(merged_file)
            if merged_file.exists()
            else build_merged_kg(include_ontology=True, settings=cfg)
        )
    return run_validation(data_graph), "run_validation"


settings = get_settings()

graph_choice = st.radio(
    "Data graph to validate",
    options=["examples", "generated/merged"],
    horizontal=True,
)

report = None
if st.button("Run SHACL validation"):
    try:
        report, fname = run_shacl(graph_choice)
        st.caption(f"Validated via {fname}('{graph_choice}').")
        st.session_state["_shacl_report"] = report
    except Exception as exc:
        st.error(f"SHACL validation failed: {exc}")

report = st.session_state.get("_shacl_report", report)

if report is not None:
    conforms = getattr(report, "conforms", None)
    violations = getattr(report, "violations", []) or []

    if conforms:
        st.success("Graph conforms to SHACL shapes.")
    else:
        st.error("Graph does NOT conform to SHACL shapes.")

    st.subheader("VCG-readiness summary")
    st.markdown(
        f"- **Conforms:** {conforms}\n"
        f"- **Violations:** {len(violations)}\n"
        f"- **VCG-ready:** {'yes' if conforms else 'no — resolve violations first'}"
    )

    if violations:
        st.subheader("Violations")
        rows = []
        for v in violations:
            if isinstance(v, dict):
                rows.append(v)
            else:
                rows.append({"violation": str(v)})
        st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("Raw validation report text"):
        st.code(getattr(report, "text", "") or "(no text)")

    if st.button("Explain with LLM"):
        try:
            from app.llm.provider import get_provider
            from app.workflows.shacl_workflow import explain_report

            # explain_report(report, provider) needs a configured provider.
            provider = get_provider()
            if not getattr(provider, "available", False):
                st.warning(
                    "No LLM provider configured — set LLM_PROVIDER and LLM_API_KEY "
                    "in .env to enable explanations."
                )
            else:
                st.write(explain_report(report, provider))
        except Exception as exc:
            st.warning(f"LLM explanation unavailable: {exc}")
else:
    st.info("Choose a graph and run validation to see results.")
