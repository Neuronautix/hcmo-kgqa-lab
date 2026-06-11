"""Advanced KGQA path: retriever -> LLM SPARQL gen -> guardrails -> execute.

Requires an available LLM provider for the generation step. Falls back to a
clear error WorkflowStep when no provider is configured.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import Settings, settings as _default_settings
from app.core.logging import get_logger
from app.core.models import (
    GroundedAnswer,
    KgqaResult,
    QueryResult,
    SparqlValidationResult,
    ValidationIssue,
    WorkflowStep,
)
from app.guardrails.injection_filter import sanitize_question
from app.guardrails.sparql_policy import validate_sparql
from app.guardrails.term_validator import validate_terms
from app.kg.sparql_client import FusekiClient, FusekiError
from app.llm.answer_generator import generate_answer
from app.llm.provider import LLMProvider, LLMProviderError, get_provider
from app.llm.sparql_generator import generate_sparql
from app.ontology.loader import load_prefixes
from app.ontology.retriever import OntologyTermRetriever
from app.ontology.term_index import TermIndex

logger = get_logger("workflows.generated_sparql")


def run_generated_sparql_kgqa(
    question: str,
    provider: Optional[LLMProvider] = None,
    retriever: Optional[OntologyTermRetriever] = None,
    index: Optional[TermIndex] = None,
    client: Optional[FusekiClient] = None,
    settings: Optional[Settings] = None,
    execute: bool = True,
) -> KgqaResult:
    """Run the generated-SPARQL KGQA workflow."""
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

    cleaned, inj_report = sanitize_question(question)
    steps.append(WorkflowStep(name="injection_filter", status="ok",
                              detail="flagged" if inj_report["flagged"] else "clean",
                              data=inj_report))

    retrieved = retriever.retrieve(cleaned, k=12)
    result.retrieved_terms = retrieved
    steps.append(WorkflowStep(name="retriever", status="ok",
                              detail=f"{len(retrieved.terms)} terms", data=retrieved.model_dump()))

    # Generate SPARQL via LLM
    try:
        sparql = generate_sparql(cleaned, retrieved, provider, prefixes)
        result.sparql = sparql
        steps.append(WorkflowStep(name="sparql_generator", status="ok",
                                  detail="generated", data={"sparql": sparql.text}))
    except LLMProviderError as exc:
        steps.append(WorkflowStep(name="sparql_generator", status="error", detail=str(exc)))
        result.answer = GroundedAnswer(
            answer="Generated-SPARQL mode requires a configured LLM provider.",
            grounded=True, caveats=[str(exc)])
        return result

    # Guardrails
    policy_result, effective = validate_sparql(sparql.text, prefixes)
    term_split = validate_terms(effective, idx, prefixes)
    used = term_split["known"] + term_split["data"]
    validation = SparqlValidationResult(
        ok=policy_result.ok and not term_split["unknown"],
        issues=list(policy_result.issues),
        used_terms=used,
    )
    if term_split["unknown"]:
        validation.issues.append(ValidationIssue(
            level="error", message=f"Unknown ontology terms: {term_split['unknown']}",
            location="query"))
    result.validation = validation
    steps.append(WorkflowStep(name="guardrails", status="ok" if validation.ok else "error",
                              detail="passed" if validation.ok else "violation",
                              data=validation.model_dump()))

    if not validation.ok:
        result.answer = GroundedAnswer(
            answer="The generated query failed safety/term validation and was not executed.",
            grounded=True,
            caveats=[i.message for i in validation.issues if i.level == "error"])
        return result

    if not execute:
        steps.append(WorkflowStep(name="execute", status="skipped", detail="execute=False"))
        return result

    client = client or FusekiClient(s)
    try:
        qresult = client.query(effective)
        result.query_result = qresult
        steps.append(WorkflowStep(name="execute", status="ok",
                                  detail=f"{qresult.count} rows", data={"count": qresult.count}))
    except FusekiError as exc:
        steps.append(WorkflowStep(name="execute", status="error", detail=str(exc)))
        result.query_result = QueryResult()
        result.answer = GroundedAnswer(answer=f"Could not execute the query: {exc}",
                                       grounded=True, caveats=[str(exc)])
        return result

    answer = generate_answer(cleaned, result.query_result, used, provider)
    result.answer = answer
    steps.append(WorkflowStep(name="answer_generator", status="ok",
                              detail="grounded" if answer.grounded else "ungrounded",
                              data=answer.model_dump()))
    return result


# Alias for UI/script compatibility
run_generated_kgqa = run_generated_sparql_kgqa
