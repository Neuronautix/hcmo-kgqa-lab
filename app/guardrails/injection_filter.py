"""Sanitise user questions against prompt-injection patterns."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

_PATTERNS: List[Tuple[str, str]] = [
    (r"(?i)ignore (all |the )?(previous|prior|above) (instructions|prompts)", "ignore_instructions"),
    (r"(?i)disregard (all |the )?(previous|prior|above)", "disregard"),
    (r"(?i)forget (everything|all|your) (instructions|context)", "forget"),
    (r"(?i)you are now\b", "role_override"),
    (r"(?i)system prompt", "system_prompt_ref"),
    (r"(?i)act as (an?|the)\b", "role_override"),
    (r"(?i)reveal (your|the) (prompt|instructions|system)", "exfiltration"),
    (r"(?i)\b(drop|delete|insert|update|clear)\s+(graph|table|all|data)\b", "sparql_write"),
    (r"```", "code_fence"),
]


def sanitize_question(question: str) -> Tuple[str, Dict[str, Any]]:
    """Return ``(cleaned_text, report)``.

    The cleaned text strips matched injection spans; the report lists which
    flags fired so the UI can surface them.
    """
    text = question or ""
    flags: List[str] = []
    cleaned = text
    for pattern, name in _PATTERNS:
        if re.search(pattern, cleaned):
            flags.append(name)
            cleaned = re.sub(pattern, " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    report = {
        "flagged": bool(flags),
        "flags": sorted(set(flags)),
        "original_length": len(text),
        "cleaned_length": len(cleaned),
    }
    return cleaned, report
