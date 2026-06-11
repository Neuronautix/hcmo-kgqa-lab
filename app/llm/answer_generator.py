"""Grounded answer generation with LLM + deterministic fallback."""

from __future__ import annotations

from typing import List, Optional

from app.core.models import GroundedAnswer, QueryResult
from app.kg.result_formatter import to_markdown
from app.llm.prompts import answer_system_prompt, answer_user_prompt
from app.llm.provider import LLMProvider, LLMProviderError


def _citations(result: QueryResult, limit: int = 20) -> List[str]:
    """Collect cell values as citation strings."""
    cites: List[str] = []
    for row in result.rows:
        for v in row.values():
            if v is None:
                continue
            sv = str(v)
            if sv and sv not in cites:
                cites.append(sv)
            if len(cites) >= limit:
                return cites
    return cites


def _fallback_answer(question: str, result: QueryResult) -> GroundedAnswer:
    if result.count == 0:
        return GroundedAnswer(
            answer="The knowledge graph contains no data matching this question.",
            grounded=True,
            citations=[],
            caveats=["No matching results were found in the knowledge graph."],
        )
    table = to_markdown(result)
    answer = (
        f"The knowledge graph returned {result.count} matching "
        f"result{'s' if result.count != 1 else ''}:\n\n{table}"
    )
    return GroundedAnswer(
        answer=answer,
        grounded=True,
        citations=_citations(result),
        caveats=[],
    )


def generate_answer(
    question: str,
    query_result: QueryResult,
    used_terms: List[str],
    provider: Optional[LLMProvider] = None,
) -> GroundedAnswer:
    """Produce a grounded NL answer from query results.

    Empty results always yield an honest grounded "no results" answer.
    """
    if query_result is None:
        query_result = QueryResult()

    # Honest empty-result handling regardless of provider.
    if query_result.count == 0:
        return _fallback_answer(question, query_result)

    if provider is None or not getattr(provider, "available", False):
        return _fallback_answer(question, query_result)

    try:
        text = provider.chat(
            [
                {"role": "system", "content": answer_system_prompt()},
                {"role": "user", "content": answer_user_prompt(question, query_result, used_terms)},
            ]
        )
    except LLMProviderError:
        return _fallback_answer(question, query_result)

    if not text or text.startswith("[null-provider]"):
        return _fallback_answer(question, query_result)

    return GroundedAnswer(
        answer=text.strip(),
        grounded=True,
        citations=_citations(query_result),
        caveats=[],
    )
