"""Generated-SPARQL workflow: validate -> repair loop (Phase 1).

Deterministic and offline. A MockProvider returns canned SPARQL so the loop is
exercised without a network or API key; execution is stubbed with a fake client.
"""

from __future__ import annotations

import pytest

VALID = (
    "PREFIX hcmo: <http://w3id.org/hcmo#>\n"
    "SELECT ?d WHERE { ?d a hcmo:Dataset } LIMIT 10"
)
UNKNOWN_TERM = (
    "PREFIX hcmo: <http://w3id.org/hcmo#>\n"
    "SELECT ?d WHERE { ?d a hcmo:NotARealClassXYZ } LIMIT 10"
)
WRITE = "DELETE WHERE { ?s ?p ?o }"


def _provider_base():
    return pytest.importorskip("app.llm.provider").LLMProvider


def _make_mock(responses):
    """A provider that returns queued responses, then a generic answer string."""
    Base = _provider_base()

    class MockProvider(Base):
        name = "mock"

        def __init__(self, queue):
            self._queue = list(queue)

        @property
        def available(self):
            return True

        def chat(self, messages, **kw):
            return self._queue.pop(0) if self._queue else "Answer based on the results."

    return MockProvider(responses)


def _fake_client(count=2):
    pytest.importorskip("pydantic")
    from app.core.models import QueryResult

    class FakeClient:
        def query(self, sparql):
            rows = [{"d": f"ex:ds{i}"} for i in range(count)]
            return QueryResult(columns=["d"], rows=rows, count=count)

    return FakeClient()


def _run(**kw):
    pytest.importorskip("rdflib")
    pytest.importorskip("pydantic")
    from app.workflows.generated_sparql_workflow import run_generated_sparql_kgqa

    return run_generated_sparql_kgqa("Which datasets exist?", **kw)


def _step_names(result):
    return [s.name for s in result.steps]


def test_valid_query_passes_first_try_and_executes():
    result = _run(provider=_make_mock([VALID]), client=_fake_client(count=3))
    assert result.validation.ok
    assert _step_names(result).count("sparql_generator") == 1  # no repair needed
    assert result.query_result is not None and result.query_result.count == 3
    assert result.answer is not None and result.answer.grounded


def test_repair_loop_fixes_unknown_term():
    # First response references an unknown ontology term; second is valid.
    result = _run(provider=_make_mock([UNKNOWN_TERM, VALID]), execute=False)
    names = _step_names(result)
    assert names.count("sparql_generator") == 2  # initial + one repair
    # The first guardrails pass rejected (warn), the second accepted (ok).
    guard_steps = [s for s in result.steps if s.name == "guardrails"]
    assert [s.status for s in guard_steps] == ["warn", "ok"]
    assert result.validation.ok
    assert "NotARealClassXYZ" not in result.sparql.text


def test_repair_gives_up_after_max_attempts():
    # Every attempt is invalid -> loop exhausts and fails closed.
    result = _run(provider=_make_mock([UNKNOWN_TERM, UNKNOWN_TERM]), execute=False)
    assert _step_names(result).count("sparql_generator") == 2
    assert not result.validation.ok
    assert any("unknown" in c.lower() for c in (result.answer.caveats or []))


def test_write_attempt_fails_fast_without_repair():
    # A forbidden write must NOT be repaired: single generation, then stop.
    result = _run(provider=_make_mock([WRITE, VALID]), execute=False)
    assert _step_names(result).count("sparql_generator") == 1  # no repair attempt
    assert not result.validation.ok
    guard = [s for s in result.steps if s.name == "guardrails"]
    assert guard and guard[-1].status == "error"


def test_no_provider_reports_provider_requirement():
    prov = pytest.importorskip("app.llm.provider")
    result = _run(provider=prov.NullProvider(), execute=False)
    assert result.answer is not None
    assert not result.answer.grounded or "provider" in result.answer.answer.lower()
