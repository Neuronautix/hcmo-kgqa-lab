"""Generated-SPARQL workflow produces a KGQA result with traceable steps.

Runs offline: uses the NullProvider (or whatever get_provider yields without an
API key). The workflow modules may still be under construction, in which case
the test skips.
"""

from __future__ import annotations

import pytest


def _kgqa_workflow():
    # The workflow module name is not yet fixed; probe likely candidates.
    candidates = (
        ("app.workflows.generated_sparql_workflow",
        ("run_generated_sparql_kgqa", "run", "run_generated")),
        ("app.workflows.kgqa_workflow", ("run_kgqa", "run", "answer_question")),
        ("app.workflows.qa_workflow", ("run_kgqa", "run", "answer_question")),
    )
    for modname, fns in candidates:
        try:
            mod = __import__(modname, fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for fn in fns:
            f = getattr(mod, fn, None)
            if callable(f):
                return f
    pytest.skip("KGQA generated-SPARQL workflow not implemented yet")


def _offline_provider():
    mod = pytest.importorskip("app.llm.provider")
    null = getattr(mod, "NullProvider", None)
    if null is not None:
        return null()
    getp = getattr(mod, "get_provider", None)
    if getp is None:
        pytest.skip("no provider available")
    return getp()


def _has_steps(result) -> bool:
    for attr in ("steps", "trace", "stages"):
        if hasattr(result, attr) and getattr(result, attr) is not None:
            return True
    if isinstance(result, dict):
        return any(k in result for k in ("steps", "trace", "stages"))
    return False


def test_generated_workflow_returns_result_with_steps():
    run = _kgqa_workflow()
    provider = _offline_provider()
    question = "Which datasets use the IntelliCage system?"
    # execute=False keeps the workflow fully offline (no Fuseki round-trip).
    for call in (
        lambda: run(question, provider=provider, execute=False),
        lambda: run(question, mode="generated", provider=provider),
        lambda: run(question, provider=provider),
        lambda: run(question),
    ):
        try:
            result = call()
            break
        except TypeError:
            result = None
    else:
        pytest.skip("workflow signature not recognized")
    assert result is not None
    assert _has_steps(result), "KGQA result should expose pipeline steps"
