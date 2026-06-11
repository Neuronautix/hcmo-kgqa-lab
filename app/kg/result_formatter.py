"""Format ``QueryResult`` objects without pandas."""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.models import QueryResult


def to_records(result: QueryResult) -> List[Dict[str, Any]]:
    """Return the rows as a list of dicts (already the native form)."""
    return list(result.rows)


def to_markdown(result: QueryResult, max_rows: int = 100) -> str:
    """Render a QueryResult as a GitHub-flavoured markdown table."""
    if not result.columns:
        return "_(no columns)_"
    if result.count == 0:
        return "_(no results)_"
    cols = result.columns
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    lines = [header, sep]
    for row in result.rows[:max_rows]:
        cells = [_cell(row.get(c)) for c in cols]
        lines.append("| " + " | ".join(cells) + " |")
    if result.count > max_rows:
        lines.append(f"_… {result.count - max_rows} more rows_")
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")
