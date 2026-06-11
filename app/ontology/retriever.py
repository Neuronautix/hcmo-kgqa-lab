"""Pure-lexical ontology term retrieval (no LLM)."""

from __future__ import annotations

from typing import Optional

from app.core.models import RetrievedTerms
from app.ontology.term_index import TermIndex


class OntologyTermRetriever:
    """Deterministic lexical retriever over a TermIndex."""

    def __init__(self, index: Optional[TermIndex] = None):
        self.index = index or TermIndex.load()

    def retrieve(self, question: str, k: int = 10) -> RetrievedTerms:
        """Return the top-k ontology terms relevant to the question."""
        terms = self.index.search(question, k=k)
        return RetrievedTerms(terms=terms, query=question)
