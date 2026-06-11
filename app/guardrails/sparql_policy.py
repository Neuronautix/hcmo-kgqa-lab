"""Read-only SPARQL policy guardrail."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from app.core.models import SparqlValidationResult, ValidationIssue

# Disallowed (write/admin) keywords — read-only policy.
_FORBIDDEN = ["INSERT", "DELETE", "DROP", "LOAD", "CLEAR", "CREATE", "ADD", "MOVE", "COPY"]
_ALLOWED_FORMS = ["SELECT", "ASK", "CONSTRUCT", "DESCRIBE"]
DEFAULT_LIMIT = 200


def _strip_comments(text: str) -> str:
    return re.sub(r"#[^\n]*", "", text)


def _query_form(text: str) -> Optional[str]:
    # First keyword after any PREFIX lines.
    body = re.sub(r"(?im)^\s*prefix\s+\S+\s*:\s*<[^>]*>\s*", "", text).strip()
    m = re.match(r"(?is)\s*(SELECT|ASK|CONSTRUCT|DESCRIBE|INSERT|DELETE|DROP|LOAD|CLEAR|CREATE)",
                 body)
    return m.group(1).upper() if m else None


def _has_limit(text: str) -> bool:
    return re.search(r"(?i)\blimit\s+\d+", text) is not None


def _inject_limit(text: str, limit: int = DEFAULT_LIMIT) -> str:
    stripped = text.rstrip().rstrip(";").rstrip()
    return f"{stripped}\nLIMIT {limit}"


def validate_sparql(
    query_text: str,
    allowed_prefixes: Optional[Dict[str, str]] = None,
) -> Tuple[SparqlValidationResult, str]:
    """Validate a SPARQL query against the read-only policy.

    Returns ``(result, effective_query)`` where ``effective_query`` may have a
    default LIMIT injected. ``result.ok`` is False for any error-level issue.
    """
    issues: List[ValidationIssue] = []
    text = query_text or ""
    clean = _strip_comments(text)

    form = _query_form(clean)
    upper = clean.upper()

    # Forbidden write/admin operations.
    for kw in _FORBIDDEN:
        if re.search(rf"(?i)\b{kw}\b", clean):
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"Forbidden operation '{kw}' is not allowed (read-only policy).",
                    location="query",
                )
            )

    if form is None or form not in _ALLOWED_FORMS:
        issues.append(
            ValidationIssue(
                level="error",
                message="Query must be a read-only SELECT/ASK/CONSTRUCT/DESCRIBE.",
                location="query",
            )
        )

    # Basic parse via rdflib (only for read forms).
    if form in ("SELECT", "ASK", "CONSTRUCT", "DESCRIBE"):
        try:
            from rdflib.plugins.sparql import prepareQuery

            prepareQuery(text)
        except Exception as exc:  # noqa: BLE001
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"SPARQL parse error: {exc}",
                    location="query",
                )
            )

    # Inject a default LIMIT for SELECT/DESCRIBE when missing.
    effective = text
    if form in ("SELECT", "DESCRIBE") and not _has_limit(clean):
        effective = _inject_limit(text)
        issues.append(
            ValidationIssue(
                level="info",
                message=f"No LIMIT present; injected default LIMIT {DEFAULT_LIMIT}.",
                location="query",
            )
        )

    ok = not any(i.level == "error" for i in issues)
    result = SparqlValidationResult(ok=ok, issues=issues, used_terms=[])
    return result, (effective if ok else text)
