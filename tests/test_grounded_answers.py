"""Grounded answer generation is honest about empty results.

With an empty QueryResult the answer generator must produce a grounded "no
results" answer rather than hallucinating. Runs offline.
"""

from __future__ import annotations

import pytest


def _answer_generator():
    candidates = (
        ("app.llm.answer_generator", ("generate_answer", "answer", "generate")),
        ("app.workflows.answer_generator", ("generate_answer", "answer", "generate")),
        ("app.guardrails.grounding_checker", ("ground_answer", "generate_answer")),
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
    pytest.skip("answer generator not implemented yet")


def _empty_query_result():
    models = pytest.importorskip("app.core.models")
    QR = getattr(models, "QueryResult", None)
    if QR is None:
        pytest.skip("QueryResult model not available")
    return QR(columns=[], rows=[], count=0)


def _offline_provider():
    mod = pytest.importorskip("app.llm.provider")
    null = getattr(mod, "NullProvider", None)
    return null() if null is not None else getattr(mod, "get_provider")()


def _is_grounded(answer) -> bool:
    for attr in ("grounded", "is_grounded"):
        if hasattr(answer, attr):
            return bool(getattr(answer, attr))
    if isinstance(answer, dict):
        return bool(answer.get("grounded", True))
    return True


def _text(answer) -> str:
    for attr in ("text", "answer", "content", "message"):
        if hasattr(answer, attr):
            return str(getattr(answer, attr))
    if isinstance(answer, dict):
        for k in ("text", "answer", "content"):
            if k in answer:
                return str(answer[k])
    return str(answer)


def test_empty_results_yield_honest_grounded_answer():
    generate = _answer_generator()
    qr = _empty_query_result()
    provider = _offline_provider()
    question = "Which datasets measure sleep duration?"

    # Try the known signature generate_answer(question, query_result,
    # used_terms, provider=...) and degrade gracefully.
    for call in (
        lambda: generate(question, qr, [], provider=provider),
        lambda: generate(question, qr, provider=provider),
        lambda: generate(question, qr),
    ):
        try:
            answer = call()
            break
        except TypeError:
            answer = None
    else:
        pytest.skip("answer generator signature not recognized")

    assert answer is not None
    assert _is_grounded(answer), "an answer over empty results must stay grounded"
    text = _text(answer).lower()
    assert any(
        kw in text for kw in ("no result", "no data", "no match", "could not find",
                            "not found", "no answer", "null-provider")
    ), f"expected an honest no-results answer, got: {text[:120]!r}"
