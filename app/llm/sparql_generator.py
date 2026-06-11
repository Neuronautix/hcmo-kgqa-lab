"""LLM-based SPARQL generation (generated-SPARQL mode)."""

from __future__ import annotations

from typing import Dict, Optional

from app.core.models import RetrievedTerms, SparqlQuery
from app.llm.prompts import sparql_system_prompt, sparql_user_prompt
from app.llm.provider import LLMProvider, LLMProviderError
from app.ontology.loader import prefix_header as _prefix_header


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _ensure_prefixes(query: str, header: str) -> str:
    """Prepend PREFIX lines that are referenced but missing."""
    lowered = query.lower()
    needed = []
    for line in header.splitlines():
        line = line.strip()
        if not line.lower().startswith("prefix"):
            continue
        try:
            pfx = line.split()[1].rstrip(":")
        except IndexError:
            continue
        if pfx.lower() + ":" in lowered and f"prefix {pfx.lower()}:" not in lowered:
            needed.append(line)
    if needed:
        return "\n".join(needed) + "\n" + query
    return query


def generate_sparql(
    question: str,
    retrieved_terms: RetrievedTerms,
    provider: Optional[LLMProvider] = None,
    prefixes: Optional[Dict[str, str]] = None,
) -> SparqlQuery:
    """Generate a SPARQL query from the question and retrieved terms.

    Requires a usable provider; raises ``LLMProviderError`` otherwise (the
    generated-SPARQL path is the advanced/online mode).
    """
    header = _prefix_header(prefixes)
    if provider is None or not getattr(provider, "available", False):
        raise LLMProviderError(
            "generate_sparql requires an available LLM provider (no API key configured)"
        )
    terms = retrieved_terms.terms if retrieved_terms else []
    raw = provider.chat(
        [
            {"role": "system", "content": sparql_system_prompt()},
            {"role": "user", "content": sparql_user_prompt(question, terms, header)},
        ]
    )
    text = _strip_fences(raw)
    text = _ensure_prefixes(text, header)
    return SparqlQuery(text=text, template_name=None, slots={})
