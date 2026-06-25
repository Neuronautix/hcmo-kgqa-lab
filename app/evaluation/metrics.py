"""Evaluation metrics for the KGQA pipeline.

All metric functions are pure and operate on lists of per-question records, so
they can be reused offline (heuristic mode) or online (LLM mode).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from app.core.config import settings
from app.core.models import KgqaResult
from app.guardrails.grounding_checker import check_grounding
from app.guardrails.sparql_policy import validate_sparql
from app.guardrails.term_validator import validate_terms
from app.llm.provider import LLMProvider, get_provider
from app.ontology.loader import load_prefixes
from app.ontology.term_index import TermIndex

_EVAL_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# Atomic metrics over a list of records
# --------------------------------------------------------------------------- #
def _rate(num: int, den: int) -> float:
    return (num / den) if den else 0.0


def intent_accuracy(records: List[Dict[str, Any]]) -> float:
    correct = sum(1 for r in records if r.get("predicted_intent") == r.get("expected_intent"))
    return _rate(correct, len(records))


def slot_accuracy(records: List[Dict[str, Any]]) -> float:
    """Fraction of records whose extracted slots cover the expected slots."""
    scored = [r for r in records if r.get("expected_slots") is not None]
    if not scored:
        return 1.0
    hits = 0
    for r in scored:
        exp = r["expected_slots"] or {}
        got = r.get("slots") or {}
        if all(str(got.get(k, "")).lower() == str(v).lower() for k, v in exp.items()):
            hits += 1
    return _rate(hits, len(scored))


def valid_sparql_rate(records: List[Dict[str, Any]]) -> float:
    return _rate(sum(1 for r in records if r.get("sparql_valid")), len(records))


def unknown_term_rate(records: List[Dict[str, Any]]) -> float:
    return _rate(sum(1 for r in records if r.get("has_unknown_terms")), len(records))


def execution_success_rate(records: List[Dict[str, Any]]) -> float:
    attempted = [r for r in records if r.get("executed") is not None]
    return _rate(sum(1 for r in attempted if r.get("executed")), len(attempted))


def empty_result_honesty(records: List[Dict[str, Any]]) -> float:
    """Among empty-result answers, fraction that honestly say 'no data'."""
    empties = [r for r in records if r.get("empty_result")]
    if not empties:
        return 1.0
    return _rate(sum(1 for r in empties if r.get("honest_no_data")), len(empties))


def groundedness(records: List[Dict[str, Any]]) -> float:
    scored = [r for r in records if r.get("grounded") is not None]
    return _rate(sum(1 for r in scored if r.get("grounded")), len(scored))


def retrieval_recall(records: List[Dict[str, Any]]) -> float:
    """Mean per-question recall of expected ontology terms by the retriever.

    For each question with a gold ``expected_iris`` set, recall is
    ``|expected ∩ retrieved| / |expected|``; the metric averages over those
    questions. Questions without gold terms are ignored (recall is undefined).
    """
    scored = [r for r in records if r.get("expected_iris")]
    if not scored:
        return 1.0
    total = 0.0
    for r in scored:
        expected = set(r.get("expected_iris") or [])
        retrieved = set(r.get("retrieved_iris") or [])
        total += _rate(len(expected & retrieved), len(expected))
    return total / len(scored)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def load_test_questions(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load an evaluation question set.

    Accepts both the NL ``test_questions.yaml`` schema (``questions:`` with
    ``expected_intent``) and the curated ``competency_questions.yaml`` schema
    (``competency_questions:`` with ``template:``). Competency entries are
    normalized so the gold template name becomes ``expected_intent``, letting
    the harness evaluate the full competency-question set unchanged.
    """
    p = Path(path) if path else _EVAL_DIR / "test_questions.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if isinstance(data, list):
        return data
    if data.get("questions"):
        return data["questions"]
    if data.get("competency_questions"):
        return [
            {
                "id": cq.get("id"),
                "question": cq.get("question", ""),
                "expected_intent": cq.get("template"),
                "description": cq.get("description"),
            }
            for cq in data["competency_questions"]
        ]
    return []


def load_expected_terms(path: Optional[Path] = None) -> Dict[str, List[str]]:
    p = Path(path) if path else _EVAL_DIR / "expected_terms.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("expected_terms", {})


# --------------------------------------------------------------------------- #
# Per-question record extraction from a KgqaResult
# --------------------------------------------------------------------------- #
def record_from_result(
    result: KgqaResult,
    expected_intent: Optional[str] = None,
    expected_slots: Optional[Dict[str, Any]] = None,
    expected_iris: Optional[List[str]] = None,
    index: Optional[TermIndex] = None,
) -> Dict[str, Any]:
    prefixes = load_prefixes()
    sparql_text = result.sparql.text if result.sparql else ""
    sparql_valid = False
    has_unknown = False
    if sparql_text:
        policy, eff = validate_sparql(sparql_text, prefixes)
        sparql_valid = policy.ok
        try:
            split = validate_terms(eff, index, prefixes)
            has_unknown = bool(split["unknown"])
        except Exception:  # noqa: BLE001
            has_unknown = False

    qr = result.query_result
    row_count = qr.count if qr is not None else None
    empty = bool(qr is not None and qr.count == 0)
    executed = None
    for step in result.steps:
        if step.name == "execute":
            executed = step.status == "ok"

    grounded = result.answer.grounded if result.answer else None
    honest = None
    if result.answer is not None and qr is not None:
        honest, _ = check_grounding(result.answer, qr)

    predicted_intent = result.intent.name if result.intent else None
    intent_correct = expected_intent is None or predicted_intent == expected_intent
    retrieved_iris = (
        [t.iri for t in result.retrieved_terms.terms] if result.retrieved_terms else []
    )

    return {
        "question": result.question,
        "expected_intent": expected_intent,
        "predicted_intent": predicted_intent,
        "intent_correct": intent_correct,
        "slots": result.intent.slots if result.intent else {},
        "expected_slots": expected_slots,
        "sparql_valid": sparql_valid,
        "has_unknown_terms": has_unknown,
        "executed": executed,
        "row_count": row_count,
        "empty_result": empty,
        "honest_no_data": honest,
        "grounded": grounded,
        "retrieved_iris": retrieved_iris,
        "expected_iris": list(expected_iris or []),
        # Overall per-question pass: correct intent, valid query, no unknown terms.
        "ok": bool(sparql_valid and not has_unknown and intent_correct),
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def workflow_for_mode(mode: str) -> Callable[..., KgqaResult]:
    """Return the KGQA workflow callable for ``mode`` (template|generated)."""
    if mode == "generated":
        from app.workflows.generated_sparql_workflow import run_generated_sparql_kgqa

        return run_generated_sparql_kgqa
    from app.workflows.template_kgqa_workflow import run_template_kgqa

    return run_template_kgqa


def run_evaluation(
    test_questions: Optional[List[Dict[str, Any]]] = None,
    workflow: Optional[Callable[..., KgqaResult]] = None,
    provider: Optional[LLMProvider] = None,
    execute: bool = True,
    mode: str = "template",
    expected_terms: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Run a workflow over the test questions and compute aggregate metrics.

    ``mode`` selects the workflow when ``workflow`` is not given:
    ``"template"`` (default) or ``"generated"``. ``expected_terms`` maps a
    question ``id`` to its gold ontology IRIs (defaults to
    ``expected_terms.yaml``) and drives the retrieval-recall metric.
    """
    if workflow is None:
        workflow = workflow_for_mode(mode)
    questions = test_questions if test_questions is not None else load_test_questions()
    provider = provider if provider is not None else get_provider(settings)
    if expected_terms is None:
        try:
            expected_terms = load_expected_terms()
        except Exception:  # noqa: BLE001
            expected_terms = {}
    try:
        index = TermIndex.load()
    except Exception:  # noqa: BLE001
        index = None

    records: List[Dict[str, Any]] = []
    for q in questions:
        question = q.get("question", "")
        qid = q.get("id")
        exp_iris = expected_terms.get(qid, []) if qid else []
        try:
            result = workflow(question, provider=provider, execute=execute)
        except Exception as exc:  # noqa: BLE001
            records.append({
                "question": question,
                "expected_intent": q.get("expected_intent"),
                "predicted_intent": None,
                "intent_correct": False,
                "sparql_valid": False,
                "has_unknown_terms": False,
                "executed": False,
                "row_count": None,
                "empty_result": False,
                "honest_no_data": None,
                "grounded": None,
                "retrieved_iris": [],
                "expected_iris": list(exp_iris),
                "ok": False,
                "error": str(exc),
            })
            continue
        records.append(
            record_from_result(
                result,
                expected_intent=q.get("expected_intent"),
                expected_slots=q.get("expected_slots"),
                expected_iris=exp_iris,
                index=index,
            )
        )

    return {
        "n": len(records),
        "mode": mode,
        "pass_rate": _rate(sum(1 for r in records if r.get("ok")), len(records)),
        "metrics": {
            "intent_accuracy": intent_accuracy(records),
            "slot_accuracy": slot_accuracy(records),
            "retrieval_recall": retrieval_recall(records),
            "valid_sparql_rate": valid_sparql_rate(records),
            "unknown_term_rate": unknown_term_rate(records),
            "execution_success_rate": execution_success_rate(records),
            "empty_result_honesty": empty_result_honesty(records),
            "groundedness": groundedness(records),
        },
        "records": records,
    }
