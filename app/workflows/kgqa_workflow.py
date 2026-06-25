"""KGQA orchestrator: template-first with automatic LLM-generated fallback.

``run_kgqa`` is the single entry point for question answering. It runs the
template path and, in ``mode="auto"``, falls back to the LLM-generated path when
the template path can't confidently answer:

  - intent is ``other`` / below a confidence threshold,
  - no SPARQL was built or it failed safety/term validation,
  - execution returned zero rows (and a provider is available).

The routing decision is recorded as a ``strategy`` WorkflowStep, and when a
fallback happens the template trace is preserved (prefixed ``template:``) ahead
of the generated trace so the UI shows both attempts.

Fallback requires an available LLM provider; without one, ``auto`` behaves like
``template`` (no dead-ends), so the offline demo is unaffected.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import Settings, settings as _default_settings
from app.core.logging import get_logger
from app.core.models import KgqaResult, WorkflowStep
from app.kg.sparql_client import FusekiClient
from app.llm.provider import LLMProvider, get_provider
from app.ontology.retriever import OntologyTermRetriever
from app.ontology.term_index import TermIndex
from app.workflows.generated_sparql_workflow import run_generated_sparql_kgqa
from app.workflows.template_kgqa_workflow import run_template_kgqa
from app.workflows.templates import template_name_for_intent

logger = get_logger("workflows.kgqa")

DEFAULT_CONFIDENCE_THRESHOLD = 0.5


def _fallback_reason(
    result: KgqaResult,
    confidence_threshold: float,
    fallback_on_empty: bool,
    execute: bool,
) -> Optional[str]:
    """Return why the template result warrants a fallback, or None to keep it."""
    intent = result.intent
    if intent is None:
        return "no intent classified"
    if intent.name == "other" or template_name_for_intent(intent.name) == "other":
        return "no matching template (intent=other)"
    if intent.confidence < confidence_threshold:
        return f"low intent confidence ({intent.confidence:.2f})"
    if result.sparql is None or not (result.sparql.text or "").strip():
        return "no SPARQL built"
    if result.validation is not None and not result.validation.ok:
        return "template query failed validation"
    if (
        execute
        and fallback_on_empty
        and result.query_result is not None
        and result.query_result.count == 0
    ):
        return "template returned 0 rows"
    return None


def _strategy_step(detail: str, **data) -> WorkflowStep:
    return WorkflowStep(name="strategy", status="ok", detail=detail, data=data or None)


def run_kgqa(
    question: str,
    provider: Optional[LLMProvider] = None,
    mode: str = "auto",
    retriever: Optional[OntologyTermRetriever] = None,
    index: Optional[TermIndex] = None,
    client: Optional[FusekiClient] = None,
    settings: Optional[Settings] = None,
    execute: bool = True,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    fallback_on_empty: bool = True,
    max_attempts: int = 2,
) -> KgqaResult:
    """Answer ``question``, routing between template and generated strategies.

    ``mode`` is ``"auto"`` (default), ``"template"`` or ``"generated"``.
    """
    s = settings or _default_settings
    provider = provider if provider is not None else get_provider(s)
    common = dict(provider=provider, retriever=retriever, index=index,
                  client=client, settings=s, execute=execute)

    if mode == "generated":
        result = run_generated_sparql_kgqa(max_attempts=max_attempts, question=question, **common)
        result.steps.insert(0, _strategy_step("generated", chosen="generated"))
        return result

    # template / auto: run the template path first.
    result = run_template_kgqa(question, **common)
    if mode == "template":
        result.steps.append(_strategy_step("template", chosen="template"))
        return result

    # auto: decide whether to fall back.
    reason = _fallback_reason(result, confidence_threshold, fallback_on_empty, execute)
    if reason is None:
        result.steps.append(_strategy_step("template", chosen="template"))
        return result

    if not getattr(provider, "available", False):
        # Want to fall back but cannot generate offline — keep the template result.
        result.steps.append(_strategy_step(
            f"template (fallback wanted: {reason}; no LLM provider)",
            chosen="template", wanted_fallback=reason, provider_available=False))
        return result

    logger.info("auto: falling back to generated-SPARQL (%s)", reason)
    gen = run_generated_sparql_kgqa(max_attempts=max_attempts, question=question, **common)

    # Merge: template trace (prefixed) -> strategy -> generated trace. The
    # generated steps keep their canonical names so downstream consumers (UI
    # highlights, eval record extraction) read the authoritative final path.
    for st in result.steps:
        st.name = f"template:{st.name}"
    strategy = _strategy_step(f"fallback:generated ({reason})",
                              chosen="generated", reason=reason)
    gen.steps = result.steps + [strategy] + gen.steps
    if gen.intent is None:
        gen.intent = result.intent
    if gen.retrieved_terms is None:
        gen.retrieved_terms = result.retrieved_terms
    return gen


# Alias for UI/script/probe compatibility.
run = run_kgqa
