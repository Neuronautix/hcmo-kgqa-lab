"""Default KGQA path: question -> template-filled SPARQL -> grounded answer.

Pipeline stages (each recorded as a WorkflowStep):
  injection_filter -> intent_classifier -> retriever -> slot_extractor ->
  fill_template (jinja2) -> sparql_policy + term_validator ->
  FusekiClient.query -> answer_generator.

Works fully offline with heuristic fallbacks when no LLM key is present, so the
demo runs against Fuseki without any API credentials.
"""

from __future__ import annotations

from typing import Optional

from jinja2 import Environment

from app.core.config import Settings, settings as _default_settings
from app.core.logging import get_logger
from app.core.models import (
    GroundedAnswer,
    KgqaResult,
    QueryResult,
    SparqlQuery,
    SparqlValidationResult,
    WorkflowStep,
)
from app.guardrails.injection_filter import sanitize_question
from app.guardrails.sparql_policy import validate_sparql
from app.guardrails.term_validator import validate_terms
from app.kg.sparql_client import FusekiClient, FusekiError
from app.llm.answer_generator import generate_answer
from app.llm.intent_classifier import classify_intent
from app.llm.provider import LLMProvider, get_provider
from app.llm.slot_extractor import extract_slots
from app.ontology.loader import load_prefixes
from app.ontology.retriever import OntologyTermRetriever
from app.ontology.term_index import TermIndex
from app.workflows.templates import load_template_source, template_name_for_intent

logger = get_logger("workflows.template_kgqa")


def _env():
    # Undefined slots render empty/false so optional {% if %} filters drop out.
    return Environment(autoescape=False)


def run_template_kgqa(
    question: str,
    provider: Optional[LLMProvider] = None,
    retriever: Optional[OntologyTermRetriever] = None,
    index: Optional[TermIndex] = None,
    client: Optional[FusekiClient] = None,
    settings: Optional[Settings] = None,
    execute: bool = True,
) -> KgqaResult:
    """Run the default template-based KGQA workflow."""
    s = settings or _default_settings
    provider = provider if provider is not None else get_provider(s)
    idx = index or (retriever.index if retriever else TermIndex.load())
    retriever = retriever or OntologyTermRetriever(idx)
    prefixes = load_prefixes()

    steps: list[WorkflowStep] = []
    result = KgqaResult(question=question, steps=steps)
    # Rebind so appends to `steps` are reflected in result.steps
    # (pydantic copies the list on construction).
    result.steps = steps

    # 1. Injection filter
    cleaned, inj_report = sanitize_question(question)
    steps.append(
        WorkflowStep(
            name="injection_filter",
            status="ok",
            detail="flagged" if inj_report["flagged"] else "clean",
            data=inj_report,
        )
    )

    # 2. Intent classification
    intent = classify_intent(cleaned, provider)
    result.intent = intent
    steps.append(
        WorkflowStep(name="intent_classifier", status="ok",
                     detail=f"{intent.name} ({intent.confidence:.2f})", data=intent.model_dump())
    )

    # 3. Term retrieval
    retrieved = retriever.retrieve(cleaned, k=10)
    result.retrieved_terms = retrieved
    steps.append(
        WorkflowStep(name="retriever", status="ok",
                     detail=f"{len(retrieved.terms)} terms", data=retrieved.model_dump())
    )

    # 4. Slot extraction
    slots = extract_slots(cleaned, intent.name, retrieved, provider)
    intent.slots = slots
    steps.append(WorkflowStep(name="slot_extractor", status="ok", detail=str(slots), data=slots))

    # 5. Fill template
    tname = template_name_for_intent(intent.name)
    try:
        source = load_template_source(intent.name, s.sparql_templates_dir)
        template = _env().from_string(source)
        rendered = template.render(**slots).strip()
        sparql = SparqlQuery(text=rendered, template_name=tname, slots=slots)
        result.sparql = sparql
        steps.append(WorkflowStep(name="fill_template", status="ok",
                                  detail=tname, data={"template": tname, "sparql": rendered}))
    except Exception as exc:  # noqa: BLE001
        steps.append(WorkflowStep(name="fill_template", status="error", detail=str(exc)))
        result.answer = GroundedAnswer(
            answer="Could not build a SPARQL query for this question.",
            grounded=True, caveats=[str(exc)])
        return result

    # 6. Guardrails: policy + term validation
    policy_result, effective_sparql = validate_sparql(sparql.text, prefixes)
    term_split = validate_terms(effective_sparql, idx, prefixes)
    used = term_split["known"] + term_split["data"]
    validation = SparqlValidationResult(
        ok=policy_result.ok and not term_split["unknown"],
        issues=policy_result.issues,
        used_terms=used,
    )
    if term_split["unknown"]:
        from app.core.models import ValidationIssue
        validation.issues.append(
            ValidationIssue(level="error",
                            message=f"Unknown ontology terms: {term_split['unknown']}",
                            location="query"))
    result.validation = validation
    steps.append(WorkflowStep(
        name="guardrails", status="ok" if validation.ok else "error",
        detail="passed" if validation.ok else "policy/term violation",
        data=validation.model_dump()))

    if not validation.ok:
        result.answer = GroundedAnswer(
            answer="The generated query failed safety/term validation and was not executed.",
            grounded=True, caveats=[i.message for i in validation.issues if i.level == "error"])
        return result

    # 7. Execute
    if not execute:
        steps.append(WorkflowStep(name="execute", status="skipped", detail="execute=False"))
        return result

    client = client or FusekiClient(s)
    try:
        qresult = client.query(effective_sparql)
        result.query_result = qresult
        steps.append(WorkflowStep(name="execute", status="ok",
                                  detail=f"{qresult.count} rows", data={"count": qresult.count}))
    except FusekiError as exc:
        steps.append(WorkflowStep(name="execute", status="error", detail=str(exc)))
        result.query_result = QueryResult()
        result.answer = GroundedAnswer(
            answer=f"Could not execute the query against Fuseki: {exc}",
            grounded=True, caveats=[str(exc)])
        return result

    # 8. Answer
    answer = generate_answer(cleaned, result.query_result, used, provider)
    result.answer = answer
    steps.append(WorkflowStep(name="answer_generator", status="ok",
                              detail="grounded" if answer.grounded else "ungrounded",
                              data=answer.model_dump()))
    return result
