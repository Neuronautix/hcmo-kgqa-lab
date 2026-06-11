"""Evaluation — run the KGQA evaluation harness and compare modes.

Selects an LLM provider/model, runs the evaluation harness over
``app/evaluation/test_questions.yaml`` and shows per-metric results
(intent accuracy, valid SPARQL rate, unknown term rate, execution success,
groundedness, latency). Allows comparing template vs generated mode.

Degrades gracefully when the evaluation backend, test set, or Fuseki are
unavailable: it shows a friendly message instead of crashing the page.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Evaluation — HCMO-KGQA", layout="wide")
st.title("Evaluation")
st.caption("Run the KGQA harness over the test questions and compare modes.")


# --------------------------------------------------------------------------- #
# Resilient backend wrappers
# --------------------------------------------------------------------------- #
def _get_settings():
    """Return the shared settings, falling back to a fresh import."""
    settings = st.session_state.get("settings")
    if settings is not None:
        return settings
    try:
        from app.core.config import get_settings

        return get_settings()
    except Exception:
        return None


def _test_questions_path(settings):
    """Best-effort locate of the evaluation test-questions file."""
    candidates = []
    if settings is not None:
        root = getattr(settings, "REPO_ROOT", None)
        if root:
            candidates.append(Path(root) / "app" / "evaluation" / "test_questions.yaml")
    here = Path(__file__).resolve()
    # app/pages/6_*.py -> app/evaluation/test_questions.yaml
    candidates.append(here.parents[1] / "evaluation" / "test_questions.yaml")
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1] if candidates else None


def run_eval(mode, provider, model, test_path):
    """Call the evaluation harness, resilient to the exact signature.

    Returns ``(result, fname)``. ``result`` is whatever the harness returns
    (ideally a list[dict] / dict of per-metric numbers).
    """
    import importlib
    import inspect

    mod = importlib.import_module("app.evaluation.metrics")
    candidates = ("run_evaluation", "evaluate", "run", "main")
    last = None
    for name in candidates:
        f = getattr(mod, name, None)
        if not callable(f):
            continue
        # Build a kwargs dict tolerant of varying parameter names.
        try:
            sig = inspect.signature(f)
            params = set(sig.parameters)
        except (TypeError, ValueError):
            params = set()

        kwargs = {}
        if "mode" in params:
            kwargs["mode"] = "template" if mode.startswith("Template") else "generated"
        if "provider" in params and provider:
            kwargs["provider"] = provider
        if "model" in params and model:
            kwargs["model"] = model
        for pname in ("test_path", "questions_path", "path", "test_questions"):
            if pname in params and test_path is not None:
                kwargs[pname] = str(test_path)
                break

        try:
            return f(**kwargs), name
        except TypeError:
            try:
                return f(), name
            except Exception as exc:  # noqa: BLE001
                last = exc
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise AttributeError(
        f"app.evaluation.metrics: none of {candidates} usable ({last}). "
        f"Available: {[n for n in dir(mod) if not n.startswith('_')]}"
    )


# --------------------------------------------------------------------------- #
# Result normalisation for display
# --------------------------------------------------------------------------- #
_METRIC_KEYS = (
    "intent_accuracy",
    "valid_sparql_rate",
    "unknown_term_rate",
    "execution_success",
    "groundedness",
    "latency",
)


def _as_metric_rows(result, label):
    """Coerce a harness result into list[dict] rows for st.dataframe."""
    # Case 1: a mapping of metric -> value.
    if isinstance(result, dict):
        # Maybe nested under a "metrics" key.
        metrics = result.get("metrics", result)
        if isinstance(metrics, dict):
            row = {"mode": label}
            row.update({k: metrics.get(k) for k in _METRIC_KEYS if k in metrics})
            # include any extra scalar metrics not in the canonical list
            for k, v in metrics.items():
                if k not in row and isinstance(v, (int, float, str, bool)):
                    row[k] = v
            return [row]
    # Case 2: a pydantic model with model_dump.
    if hasattr(result, "model_dump"):
        return _as_metric_rows(result.model_dump(), label)
    # Case 3: already a list of dict rows.
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return [{"mode": label, **r} for r in result]
    # Fallback: stringify.
    return [{"mode": label, "result": str(result)}]


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
settings = _get_settings()
default_provider = getattr(settings, "LLM_PROVIDER", "openai") if settings else "openai"
default_model = getattr(settings, "LLM_MODEL", None) if settings else None

test_path = _test_questions_path(settings)
if test_path is not None and test_path.exists():
    st.caption(f"Test set: `{test_path}`")
else:
    st.warning(
        "Test-questions file not found yet "
        f"(expected at `{test_path}`). The harness may use its own default."
    )

col1, col2 = st.columns(2)
with col1:
    provider = st.text_input("LLM provider", value=str(default_provider))
with col2:
    model = st.text_input("LLM model (optional)", value=str(default_model or ""))

modes = st.multiselect(
    "Modes to evaluate",
    ["Template-first (default)", "Generated-SPARQL (experimental)"],
    default=["Template-first (default)"],
    help="Select two modes to compare template vs generated SPARQL.",
)

if st.button("Run evaluation", type="primary"):
    if not modes:
        st.warning("Select at least one mode to evaluate.")
    else:
        all_rows = []
        for mode in modes:
            label = "template" if mode.startswith("Template") else "generated"
            with st.status(f"Running evaluation — {label} mode…", expanded=True) as status:
                try:
                    result, fname = run_eval(mode, provider or None, model or None, test_path)
                    rows = _as_metric_rows(result, label)
                    all_rows.extend(rows)
                    status.update(label=f"{label}: done via {fname}()", state="complete")
                except ModuleNotFoundError:
                    status.update(
                        label=f"{label}: evaluation backend not available yet",
                        state="error",
                    )
                    st.error(
                        "app.evaluation.metrics is not available. The evaluation "
                        "harness has not been implemented yet by the backend."
                    )
                except Exception as exc:  # noqa: BLE001
                    status.update(label=f"{label}: failed", state="error")
                    st.error(f"Evaluation failed for {label} mode: {exc}")

        if all_rows:
            st.subheader("Per-metric results")
            st.dataframe(all_rows, use_container_width=True, hide_index=True)
            if len(all_rows) > 1:
                st.caption("Compare rows across modes to assess template vs generated.")
else:
    st.info(
        "Pick provider/model and one or more modes, then run the harness. "
        "Metrics: intent accuracy, valid SPARQL rate, unknown term rate, "
        "execution success, groundedness, latency."
    )
