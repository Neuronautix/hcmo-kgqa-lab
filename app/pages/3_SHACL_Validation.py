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
    """Call the shacl workflow with the most likely function name."""
    import importlib

    mod = importlib.import_module("app.workflows.shacl_workflow")
    candidates = ("run_shacl", "validate_graph", "run_shacl_validation", "validate", "run")
    last = None
    for name in candidates:
        f = getattr(mod, name, None)
        if callable(f):
            try:
                return f(graph_choice), name
            except TypeError:
                try:
                    return f(), name
                except Exception as exc:
                    last = exc
            except Exception as exc:
                last = exc
    raise AttributeError(
        f"shacl_workflow: none of {candidates} usable ({last}). "
        f"Available: {[n for n in dir(mod) if not n.startswith('_')]}"
    )


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
            import importlib

            mod = importlib.import_module("app.workflows.shacl_workflow")
            explainer = None
            for name in ("explain_report", "explain", "explain_with_llm"):
                explainer = getattr(mod, name, None)
                if callable(explainer):
                    break
            if explainer is None:
                st.warning("No LLM explanation function found in shacl_workflow.")
            else:
                st.write(explainer(report))
        except Exception as exc:
            st.warning(f"LLM explanation unavailable: {exc}")
else:
    st.info("Choose a graph and run validation to see results.")
