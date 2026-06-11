"""Workflow: run SHACL on a graph, optionally LLM-explain the report."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from rdflib import Graph

from app.core.models import ShaclReport
from app.llm.provider import LLMProvider, LLMProviderError
from app.shacl.readiness import vcg_readiness_report
from app.shacl.validator import run_validation


def run_shacl_workflow(
    data_graph: Union[str, Path, Graph],
    provider: Optional[LLMProvider] = None,
    explain: bool = False,
) -> dict:
    """Validate a graph and return report + readiness + optional explanation."""
    report: ShaclReport = run_validation(data_graph)
    readiness = vcg_readiness_report(data_graph)
    out = {
        "report": report,
        "readiness": readiness,
        "explanation": None,
    }
    if explain and provider is not None and getattr(provider, "available", False):
        out["explanation"] = explain_report(report, provider)
    return out


def explain_report(report: ShaclReport, provider: LLMProvider) -> str:
    """Ask the LLM to summarise a SHACL report in plain language."""
    if report.conforms:
        return "The data graph conforms to all SHACL shapes; no issues found."
    violations = "\n".join(
        f"- focus={v.get('focusNode')} path={v.get('resultPath')} :: {v.get('message')}"
        for v in report.violations[:50]
    )
    try:
        return provider.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You explain SHACL validation reports for a biomedical "
                        "knowledge graph in clear, actionable language. List what "
                        "metadata is missing and how to fix it. Be concise."
                    ),
                },
                {"role": "user", "content": f"SHACL violations:\n{violations}\n\nExplanation:"},
            ]
        )
    except LLMProviderError:
        return report.text
