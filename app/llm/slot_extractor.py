"""Slot extraction with LLM + heuristic fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from app.core.models import OntologyTerm, RetrievedTerms
from app.llm.prompts import slot_system_prompt, slot_user_prompt
from app.llm.provider import LLMProvider, LLMProviderError

# Known data values for heuristic extraction (from the example KG).
_SPECIES = ["mouse", "mus musculus", "rat", "rattus"]
_STRAINS = ["b6", "c57bl/6", "c57bl6", "balb/c", "balbc", "wistar"]
_SYSTEMS = ["digigait", "phenomaster", "digitalventicage", "intellicage", "laboras"]
_METRICS = ["distance", "locomotor", "sleep", "food", "water", "activity", "gait"]


def heuristic_slots(question: str, intent: str, retrieved: RetrievedTerms) -> Dict[str, Any]:
    """Best-effort slot extraction via keyword matching."""
    q = (question or "").lower()
    slots: Dict[str, Any] = {}

    for s in _SYSTEMS:
        if s in q:
            slots["system_name"] = s
            break
    for s in _STRAINS:
        if s in q:
            slots["strain"] = s
            break
    for s in _SPECIES:
        if s in q:
            slots["species"] = s
            break
    for m in _METRICS:
        if m in q:
            slots["metric"] = m
            break

    # Capture an explicit dataset reference so dataset-scoped queries actually
    # filter (and a non-existent dataset honestly returns no rows). Only bind on
    # an unambiguous reference: an HCMO dataset identifier ("HCMO-DS-0001") or a
    # dataset IRI local name ("ds_sleep2023"). A generic mention of "datasets"
    # must NOT set this slot.
    dm = re.search(r"\bHCMO-DS-\d+\b", question or "", re.IGNORECASE)
    if not dm:
        dm = re.search(r"\bds[_-][a-z0-9_]+\b", q)
    if dm:
        slots["dataset"] = dm.group(0)

    # Capture a quoted phrase if present, useful for titles/experiment names.
    m = re.search(r'"([^"]+)"', question or "")
    if m:
        slots["phrase"] = m.group(1)
    return slots


def extract_slots(
    question: str,
    intent: str,
    retrieved_terms: RetrievedTerms,
    provider: Optional[LLMProvider] = None,
) -> Dict[str, Any]:
    """Extract slots, using the LLM when available else heuristics."""
    if provider is None or not getattr(provider, "available", False):
        return heuristic_slots(question, intent, retrieved_terms)
    terms = retrieved_terms.terms if retrieved_terms else []
    try:
        raw = provider.chat(
            [
                {"role": "system", "content": slot_system_prompt()},
                {"role": "user", "content": slot_user_prompt(question, intent, terms)},
            ]
        )
    except LLMProviderError:
        return heuristic_slots(question, intent, retrieved_terms)
    parsed = _parse_json(raw)
    if not parsed:
        return heuristic_slots(question, intent, retrieved_terms)
    return parsed


def _parse_json(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}
