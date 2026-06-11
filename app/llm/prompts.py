"""Prompt builders for intent, slots, SPARQL generation and answers.

Plain string functions; no provider calls here.
"""

from __future__ import annotations

from typing import List

from app.core.models import OntologyTerm, QueryResult

# Canonical intent labels (the 5 competency-question intents + 'other').
INTENT_LABELS = [
    "datasets_by_system",
    "metrics_for_experiment",
    "experiments_by_species",
    "vcg_readiness",
    "systems_overview",
    "other",
]


def _terms_block(terms: List[OntologyTerm]) -> str:
    lines = []
    for t in terms:
        lines.append(f"- {t.iri} ({t.term_type}) label='{t.label}' :: {t.comment or ''}")
    return "\n".join(lines) if lines else "(no terms retrieved)"


def intent_system_prompt() -> str:
    return (
        "You are an intent classifier for a knowledge-graph QA system about "
        "home cage monitoring (HCMO) experiments. Classify the user's question "
        "into exactly one of these intents:\n"
        + "\n".join(f"- {l}" for l in INTENT_LABELS)
        + "\nRespond with ONLY the intent label, nothing else."
    )


def intent_user_prompt(question: str) -> str:
    return f"Question: {question}\nIntent:"


def slot_system_prompt() -> str:
    return (
        "You extract slot values from a question for a home cage monitoring "
        "knowledge graph. Return a compact JSON object of slot_name -> value. "
        "Use slots such as system_name, species, strain, experiment, metric. "
        "Return ONLY JSON."
    )


def slot_user_prompt(question: str, intent: str, terms: List[OntologyTerm]) -> str:
    return (
        f"Intent: {intent}\nQuestion: {question}\n"
        f"Relevant ontology terms:\n{_terms_block(terms)}\n"
        "JSON slots:"
    )


def sparql_system_prompt() -> str:
    return (
        "You are a SPARQL expert. Generate a single read-only SPARQL query "
        "(SELECT/ASK/CONSTRUCT/DESCRIBE only) answering the question over the "
        "HCMO knowledge graph. Use ONLY the supplied ontology terms and "
        "prefixes. Always include all needed PREFIX lines and a LIMIT. "
        "Return ONLY the SPARQL query, no prose, no markdown fences."
    )


def sparql_user_prompt(question: str, terms: List[OntologyTerm], prefix_header: str) -> str:
    return (
        f"Prefixes:\n{prefix_header}\n\n"
        f"Available ontology terms:\n{_terms_block(terms)}\n\n"
        f"Question: {question}\n\nSPARQL:"
    )


def answer_system_prompt() -> str:
    return (
        "You answer questions about home cage monitoring experiments STRICTLY "
        "from the provided SPARQL query results. Do not invent facts. If the "
        "results are empty, say clearly that the knowledge graph has no matching "
        "data. Cite the relevant values from the results. Be concise."
    )


def answer_user_prompt(question: str, result: QueryResult, used_terms: List[str]) -> str:
    from app.kg.result_formatter import to_markdown

    table = to_markdown(result)
    terms = ", ".join(used_terms) if used_terms else "(none)"
    return (
        f"Question: {question}\n\n"
        f"Ontology terms used: {terms}\n\n"
        f"Query results ({result.count} rows):\n{table}\n\n"
        "Answer (grounded only in the results above):"
    )
