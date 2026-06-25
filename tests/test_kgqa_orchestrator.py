"""Auto-fallback orchestrator (fallback plan Phase 2).

Deterministic and offline. A content-aware MockProvider answers intent/slot/
SPARQL/answer prompts by inspecting the system prompt, so the template and
generated paths run without a network or API key.
"""

from __future__ import annotations

import pytest

VALID = (
    "PREFIX hcmo: <http://w3id.org/hcmo#>\n"
    "SELECT ?d WHERE { ?d a hcmo:Dataset } LIMIT 10"
)


def _provider_base():
    return pytest.importorskip("app.llm.provider").LLMProvider


def _mock(intent="vcg_readiness", sparqls=None):
    Base = _provider_base()

    class MockProvider(Base):
        name = "mock"

        def __init__(self):
            self._intent = intent
            self._sparqls = list(sparqls or [VALID])

        @property
        def available(self):
            return True

        def chat(self, messages, **kw):
            sysmsg = (messages[0].get("content", "") if messages else "").lower()
            if "intent classifier" in sysmsg:
                return self._intent
            if "extract slot" in sysmsg:
                return "{}"
            if "sparql expert" in sysmsg:
                return self._sparqls.pop(0) if self._sparqls else VALID
            if "answer questions" in sysmsg:
                return "Grounded answer from results."
            return ""

    return MockProvider()


def _fake_client(count=2):
    pytest.importorskip("pydantic")
    from app.core.models import QueryResult

    class FakeClient:
        def query(self, sparql):
            rows = [{"d": f"ex:ds{i}"} for i in range(count)]
            return QueryResult(columns=["d"], rows=rows, count=count)

    return FakeClient()


def _run(question="Which datasets are VCG-ready?", **kw):
    pytest.importorskip("rdflib")
    pytest.importorskip("pydantic")
    from app.workflows.kgqa_workflow import run_kgqa

    return run_kgqa(question, **kw)


def _names(result):
    return [s.name for s in result.steps]


def _strategy(result):
    return next((s for s in result.steps if s.name == "strategy"), None)


def test_auto_keeps_template_when_confident_and_nonempty():
    result = _run(provider=_mock(intent="vcg_readiness"), client=_fake_client(count=3))
    assert _strategy(result).detail == "template"
    assert "sparql_generator" not in _names(result)  # no fallback happened


def test_auto_falls_back_on_other_intent():
    result = _run(provider=_mock(intent="other", sparqls=[VALID]), client=_fake_client(count=2))
    strat = _strategy(result)
    assert "fallback:generated" in strat.detail
    assert "intent=other" in strat.detail
    # Both traces are present: template attempt (prefixed) + generated path.
    assert "template:injection_filter" in _names(result)
    assert "sparql_generator" in _names(result)


def test_auto_falls_back_on_empty_results():
    # Valid intent + valid template, but zero rows -> fall back.
    result = _run(provider=_mock(intent="vcg_readiness", sparqls=[VALID]),
                  client=_fake_client(count=0))
    strat = _strategy(result)
    assert "fallback:generated" in strat.detail
    assert "0 rows" in strat.detail


def test_auto_without_provider_stays_template():
    prov = pytest.importorskip("app.llm.provider")
    # Off-topic question -> heuristic intent "other", but no provider to generate.
    result = _run(question="Tell me about quantum physics.",
                  provider=prov.NullProvider(), execute=False)
    strat = _strategy(result)
    assert strat.data.get("chosen") == "template"
    assert "no LLM provider" in strat.detail
    assert "sparql_generator" not in _names(result)


def test_mode_generated_passthrough():
    result = _run(mode="generated", provider=_mock(sparqls=[VALID]), execute=False)
    assert "sparql_generator" in _names(result)
    assert _strategy(result).detail == "generated"


def test_mode_template_passthrough_no_fallback():
    result = _run(mode="template", provider=_mock(intent="vcg_readiness"), execute=False)
    assert _strategy(result).detail == "template"
    assert "sparql_generator" not in _names(result)
