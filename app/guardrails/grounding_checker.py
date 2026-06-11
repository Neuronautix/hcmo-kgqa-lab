"""Check that an answer's claims are grounded in the query results."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.core.models import GroundedAnswer, QueryResult


def _result_values(result: QueryResult) -> List[str]:
    values: List[str] = []
    for row in result.rows:
        for v in row.values():
            if v is None:
                continue
            values.append(str(v).lower())
    return values


def _candidate_claims(text: str) -> List[str]:
    """Extract quoted strings and capitalised/identifier-like tokens."""
    claims = re.findall(r'"([^"]+)"', text)
    claims += re.findall(r"\b([A-Z][A-Za-z0-9_\-]{3,})\b", text)
    claims += re.findall(r"\b([A-Za-z]+-[A-Za-z0-9-]+)\b", text)  # e.g. HCMO-DS-0001
    return [c for c in claims if len(c) >= 4]


def check_grounding(answer: GroundedAnswer, result: QueryResult) -> Tuple[bool, Dict[str, Any]]:
    """Return ``(grounded, report)``.

    A simple substring check: every concrete claim token in the answer should
    appear among the result values. Empty results require the answer to state
    that there is no matching data.
    """
    text = answer.answer or ""
    if result is None or result.count == 0:
        honest = bool(re.search(r"(?i)no (matching )?(data|results)|not (found|present)|empty", text))
        return honest, {
            "mode": "empty_result",
            "honest_no_data": honest,
            "unsupported": [],
        }

    values = _result_values(result)
    blob = " ".join(values)
    claims = _candidate_claims(text)
    unsupported = [c for c in claims if c.lower() not in blob]
    grounded = len(unsupported) == 0
    return grounded, {
        "mode": "results",
        "checked_claims": claims,
        "unsupported": unsupported,
        "n_result_values": len(values),
    }
