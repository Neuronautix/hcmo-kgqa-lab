"""In-memory index over ontology terms with lightweight keyword search."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.core.models import OntologyTerm

logger = get_logger("ontology.term_index")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _local_name(iri: str) -> str:
    for sep in ("#", "/"):
        if sep in iri:
            return iri.rsplit(sep, 1)[-1]
    return iri


def _split_camel(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name)


def tokenize(text: str) -> List[str]:
    """Lowercase token list (camelCase aware)."""
    if not text:
        return []
    text = _split_camel(text)
    return _TOKEN_RE.findall(text.lower())


class TermIndex:
    """Index of ontology terms supporting deterministic keyword search."""

    def __init__(self, terms: Optional[List[OntologyTerm]] = None):
        self._terms: List[OntologyTerm] = list(terms or [])
        self._by_iri: Dict[str, OntologyTerm] = {t.iri: t for t in self._terms}
        self._tokens: Dict[str, set] = {}
        self._index_tokens()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_json(cls, path: Optional[Path] = None) -> "TermIndex":
        """Load terms from ``hcmo_terms.json``.

        Accepts either a list of term dicts or a profile-style dict.
        """
        json_path = Path(path) if path else Path(settings.terms_json_path)
        with open(json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        terms = cls._coerce_terms(data)
        return cls(terms)

    @classmethod
    def from_ontology(cls) -> "TermIndex":
        """Build the index directly from the ontology graph."""
        from app.ontology.loader import load_ontology
        from app.ontology.profiler import build_profile, profile_to_terms

        graph = load_ontology()
        profile = build_profile(graph)
        return cls(profile_to_terms(profile))

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "TermIndex":
        """Load from JSON, falling back to building from the ontology."""
        json_path = Path(path) if path else Path(settings.terms_json_path)
        if json_path.exists():
            try:
                return cls.from_json(json_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load %s: %s; rebuilding", json_path, exc)
        return cls.from_ontology()

    @staticmethod
    def _coerce_terms(data) -> List[OntologyTerm]:
        terms: List[OntologyTerm] = []
        if isinstance(data, dict) and any(
            k in data for k in ("classes", "object_properties", "datatype_properties")
        ):
            from app.ontology.profiler import profile_to_terms

            return profile_to_terms(data)
        if isinstance(data, dict) and "terms" in data:
            data = data["terms"]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    terms.append(
                        OntologyTerm(
                            iri=item.get("iri") or item.get("uri") or "",
                            label=item.get("label"),
                            term_type=item.get("term_type") or item.get("type") or "unknown",
                            comment=item.get("comment"),
                        )
                    )
        return [t for t in terms if t.iri]

    def _index_tokens(self) -> None:
        self._tokens = {}
        for t in self._terms:
            toks = set(tokenize(t.label or ""))
            toks |= set(tokenize(_local_name(t.iri)))
            toks |= set(tokenize(t.comment or ""))
            self._tokens[t.iri] = toks

    # ------------------------------------------------------------------ #
    # Access
    # ------------------------------------------------------------------ #
    def all_terms(self) -> List[OntologyTerm]:
        return list(self._terms)

    def by_iri(self, iri: str) -> Optional[OntologyTerm]:
        return self._by_iri.get(iri)

    def __len__(self) -> int:
        return len(self._terms)

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def search(self, query: str, k: int = 10) -> List[OntologyTerm]:
        """Deterministic keyword search by token overlap + substring bonus."""
        q_tokens = set(tokenize(query))
        q_lower = (query or "").lower()
        scored = []
        for t in self._terms:
            toks = self._tokens.get(t.iri, set())
            overlap = len(q_tokens & toks)
            score = float(overlap)
            # Substring bonus on label / local name.
            for field in (t.label or "", _local_name(t.iri)):
                fl = field.lower()
                if fl and (fl in q_lower or any(tok in fl for tok in q_tokens)):
                    score += 0.5
            if score > 0:
                scored.append((score, t))
        scored.sort(key=lambda pair: (-pair[0], pair[1].iri))
        return [t for _, t in scored[:k]]
