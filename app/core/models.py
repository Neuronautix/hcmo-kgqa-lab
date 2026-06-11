"""Pydantic models shared across backend layers and the Streamlit UI.

All models are plain, JSON-serializable (``model_dump()``) pydantic v2 models
so the UI and evaluation layers can consume them without extra glue.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Ontology / retrieval
# --------------------------------------------------------------------------- #
class OntologyTerm(BaseModel):
    """A single ontology term (class or property)."""

    iri: str
    label: Optional[str] = None
    term_type: str = "unknown"  # class | object_property | datatype_property | ...
    comment: Optional[str] = None


class RetrievedTerms(BaseModel):
    """Result of lexical ontology-term retrieval for a question."""

    terms: List[OntologyTerm] = Field(default_factory=list)
    query: str = ""


# --------------------------------------------------------------------------- #
# Intent / SPARQL
# --------------------------------------------------------------------------- #
class Intent(BaseModel):
    """Classified intent for a natural-language question."""

    name: str = "other"
    confidence: float = 0.0
    slots: Dict[str, Any] = Field(default_factory=dict)


class SparqlQuery(BaseModel):
    """A SPARQL query, either template-filled or LLM-generated."""

    text: str = ""
    template_name: Optional[str] = None
    slots: Dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
class ValidationIssue(BaseModel):
    """A single guardrail / validation issue."""

    level: str = "info"  # info | warning | error
    message: str = ""
    location: Optional[str] = None


class SparqlValidationResult(BaseModel):
    """Outcome of running SPARQL guardrails."""

    ok: bool = True
    issues: List[ValidationIssue] = Field(default_factory=list)
    used_terms: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Query execution
# --------------------------------------------------------------------------- #
class QueryResult(BaseModel):
    """Tabular result of a SPARQL SELECT/ASK query."""

    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    raw: Optional[Any] = None

    @property
    def is_empty(self) -> bool:
        return self.count == 0


# --------------------------------------------------------------------------- #
# SHACL
# --------------------------------------------------------------------------- #
class ShaclReport(BaseModel):
    """Result of a pyshacl validation run."""

    conforms: bool = True
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    text: str = ""


# --------------------------------------------------------------------------- #
# Answer
# --------------------------------------------------------------------------- #
class GroundedAnswer(BaseModel):
    """A natural-language answer grounded in KG results."""

    answer: str = ""
    grounded: bool = False
    citations: List[str] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Workflow orchestration
# --------------------------------------------------------------------------- #
class WorkflowStep(BaseModel):
    """A single stage in a workflow, for UI tracing."""

    name: str
    status: str = "pending"  # pending | ok | error | skipped
    detail: str = ""
    data: Optional[Any] = None


class KgqaResult(BaseModel):
    """Full result of a KGQA workflow run, surfaced in the UI."""

    question: str
    intent: Optional[Intent] = None
    retrieved_terms: Optional[RetrievedTerms] = None
    sparql: Optional[SparqlQuery] = None
    validation: Optional[SparqlValidationResult] = None
    query_result: Optional[QueryResult] = None
    answer: Optional[GroundedAnswer] = None
    steps: List[WorkflowStep] = Field(default_factory=list)
