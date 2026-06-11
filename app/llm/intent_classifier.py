"""Intent classification with LLM + deterministic heuristic fallback."""

from __future__ import annotations

from typing import Optional

from app.core.models import Intent
from app.llm.prompts import INTENT_LABELS, intent_system_prompt, intent_user_prompt
from app.llm.provider import LLMProvider, LLMProviderError

# Keyword cues for the heuristic fallback.
_HEURISTICS = [
    ("vcg_readiness", ["vcg", "ready", "readiness", "missing", "metadata", "complete", "reuse"]),
    ("datasets_by_system", ["dataset", "system", "platform", "digigait", "phenomaster", "produced by"]),
    ("metrics_for_experiment", ["metric", "measure", "readout", "behavioral", "behaviour", "distance", "sleep"]),
    ("experiments_by_species", ["species", "strain", "mouse", "mice", "b6", "balb", "wistar", "cohort", "animal"]),
    ("systems_overview", ["systems", "vendor", "list systems", "which systems", "available systems"]),
]


def heuristic_intent(question: str) -> Intent:
    """Deterministic keyword-based intent classifier."""
    q = (question or "").lower()
    best_name = "other"
    best_score = 0
    for name, cues in _HEURISTICS:
        score = sum(1 for c in cues if c in q)
        if score > best_score:
            best_score, best_name = score, name
    confidence = min(0.5 + 0.15 * best_score, 0.95) if best_score else 0.3
    return Intent(name=best_name, confidence=confidence, slots={})


def classify_intent(question: str, provider: Optional[LLMProvider] = None) -> Intent:
    """Classify a question's intent, falling back to heuristics offline."""
    if provider is None or not getattr(provider, "available", False):
        return heuristic_intent(question)
    try:
        raw = provider.chat(
            [
                {"role": "system", "content": intent_system_prompt()},
                {"role": "user", "content": intent_user_prompt(question)},
            ]
        )
    except LLMProviderError:
        return heuristic_intent(question)
    label = _normalize(raw)
    if label not in INTENT_LABELS:
        return heuristic_intent(question)
    return Intent(name=label, confidence=0.9, slots={})


def _normalize(raw: str) -> str:
    text = (raw or "").strip().lower()
    for label in INTENT_LABELS:
        if label in text:
            return label
    return "other"
