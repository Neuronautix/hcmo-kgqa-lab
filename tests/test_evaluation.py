"""Evaluation harness produces complete, structured metrics offline.

Runs fully offline with ``execute=False`` and the NullProvider, so no Fuseki
or LLM key is required. Exercises both the NL test set and the full curated
competency-question set.
"""

from __future__ import annotations

import pytest

EXPECTED_METRIC_KEYS = {
    "intent_accuracy",
    "slot_accuracy",
    "retrieval_recall",
    "valid_sparql_rate",
    "unknown_term_rate",
    "execution_success_rate",
    "empty_result_honesty",
    "groundedness",
}


def _metrics_mod():
    pytest.importorskip("rdflib")
    pytest.importorskip("pydantic")
    return pytest.importorskip("app.evaluation.metrics")


def _null_provider():
    prov = pytest.importorskip("app.llm.provider")
    return prov.NullProvider()


def test_run_evaluation_reports_all_metrics_offline():
    m = _metrics_mod()
    report = m.run_evaluation(execute=False, provider=_null_provider())

    assert report["n"] == 6
    assert report["mode"] == "template"
    assert set(report["metrics"]) == EXPECTED_METRIC_KEYS
    # Every metric is a rate in [0, 1].
    for key, val in report["metrics"].items():
        assert 0.0 <= val <= 1.0, f"{key} out of range: {val}"
    assert 0.0 <= report["pass_rate"] <= 1.0

    # Records carry the completed per-question fields.
    rec = report["records"][0]
    for field in ("ok", "predicted_intent", "retrieved_iris", "expected_iris", "intent_correct"):
        assert field in rec

    # The retriever should recover at least some gold terms.
    assert report["metrics"]["retrieval_recall"] > 0.0


def test_retrieval_recall_is_perfect_and_zero_at_extremes():
    m = _metrics_mod()
    full = [{"expected_iris": ["a", "b"], "retrieved_iris": ["a", "b", "c"]}]
    none = [{"expected_iris": ["a", "b"], "retrieved_iris": ["x"]}]
    assert m.retrieval_recall(full) == 1.0
    assert m.retrieval_recall(none) == 0.0
    # No gold terms -> undefined -> treated as 1.0 (does not penalize).
    assert m.retrieval_recall([{"retrieved_iris": ["a"]}]) == 1.0


def test_competency_question_set_is_loadable_and_normalized():
    m = _metrics_mod()
    from app.core.config import settings

    cq_path = __import__("pathlib").Path(settings.REPO_ROOT) / "sparql" / "competency_questions.yaml"
    questions = m.load_test_questions(cq_path)
    assert len(questions) == 5
    # template -> expected_intent normalization, ids preserved.
    assert all(q.get("expected_intent") for q in questions)
    assert {q["id"] for q in questions} == {"CQ001", "CQ002", "CQ003", "CQ004", "CQ005"}


def test_run_evaluation_over_full_competency_set_offline():
    m = _metrics_mod()
    from app.core.config import settings

    cq_path = __import__("pathlib").Path(settings.REPO_ROOT) / "sparql" / "competency_questions.yaml"
    questions = m.load_test_questions(cq_path)
    report = m.run_evaluation(questions, execute=False, provider=_null_provider())
    assert report["n"] == 5
    assert set(report["metrics"]) == EXPECTED_METRIC_KEYS


def test_workflow_for_mode_returns_callables():
    m = _metrics_mod()
    assert callable(m.workflow_for_mode("template"))
    assert callable(m.workflow_for_mode("generated"))
