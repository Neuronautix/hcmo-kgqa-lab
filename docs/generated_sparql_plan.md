# Plan: wire the LLM-generated SPARQL fallback end-to-end

## Status today

The generated-SPARQL path already exists and is partially wired:

- `app/llm/sparql_generator.py` — `generate_sparql(question, retrieved_terms, provider, prefixes)` builds a query from the retrieved HCMO terms and a prompt.
- `app/workflows/generated_sparql_workflow.py` — `run_generated_sparql_kgqa(...)` runs retrieval → LLM generation → guardrails → execute → grounded answer, with a full `steps` trace.
- The KGQA Workflow page exposes it as a manually-selected **"Generated-SPARQL (experimental)"** radio mode.

What makes it **not** end-to-end:

1. **No automatic fallback.** The template path (`run_template_kgqa`) never delegates to the generated path. When intent classification returns `other` (or a template renders an empty/invalid query), the run just fails with *"Could not build a SPARQL query."* The README's documented `no match → LLM generation` edge is not implemented — the user must switch modes by hand. The completed eval harness quantifies this gap: on the curated competency set, intent accuracy is **0.2** (4 of 5 questions map to the wrong template), and those are exactly the questions the fallback should catch.
2. **Hard failure offline.** `generate_sparql` raises `LLMProviderError` when no provider is available, and the workflow surfaces a dead-end answer. There is no deterministic degradation for the no-key/demo path.
3. **No validate→repair loop.** A generated query that fails the read-only policy or references unknown HCMO terms is rejected outright; the model never gets a second attempt with the validator feedback.
4. **Thin test coverage.** `tests/test_generated_sparql.py` only asserts that *some* steps exist with the NullProvider; there is no end-to-end assertion that a generated query is valid, term-checked, executed, and grounded (with a mock provider).

## Goal

One question-answering entry point that **prefers templates and falls back to LLM generation automatically**, degrades safely without a key, repairs near-miss queries, and is covered by a deterministic test using a mock provider.

## Design

### A. Confidence-gated automatic fallback

Add an orchestrator `run_kgqa(question, mode="auto", ...)` (new `app/workflows/kgqa_workflow.py`, or extend the template workflow):

- `mode="template"` / `mode="generated"` — force one path (today's behavior).
- `mode="auto"` (new default for the UI):
  1. Run the template path.
  2. **Fall back to generated** when any trigger fires: intent is `other` / below a confidence threshold; `template_name_for_intent` has no entry; the rendered query fails guardrails; or execution returns 0 rows *and* a provider is available.
  3. Record the decision as a `WorkflowStep(name="strategy", detail="template" | "fallback:generated", ...)` so the trace shows *why* it switched.
- Merge both traces so the UI shows the attempted template step **and** the generated step.

### B. Safe degradation without a provider

- In `generate_sparql`, keep raising `LLMProviderError` (correct), but in the orchestrator catch it and return the template path's honest failure rather than a generated dead-end.
- Surface provider availability in the trace (`strategy` step detail: `"no provider — template only"`), so the demo is self-explanatory offline.

### C. Validate → repair retry loop

In `generated_sparql_workflow`, wrap generation + guardrails in a bounded loop (`max_attempts=2`):

1. Generate → validate policy + terms.
2. If it fails, re-prompt the model with the specific issues (`"Your query referenced unknown term hcmo:Foo; valid terms are: ..."`, `"writes are forbidden; use SELECT"`), reusing the retrieved-term list.
3. Stop at the first valid query or after `max_attempts`; record each attempt as a step.

Add a `repair_user_prompt(question, terms, header, issues)` to `app/llm/prompts.py`.

### D. Tests (deterministic, offline)

Add a `MockProvider(LLMProvider)` test helper that returns a canned SPARQL string (and, for the repair test, an invalid-then-valid pair).

- `test_generated_end_to_end_with_mock`: valid query → guardrails ok → execute (monkeypatched `FusekiClient` returning a fixed `QueryResult`) → grounded answer with citations.
- `test_generated_repair_loop`: first response references an unknown term, second is valid; assert two `sparql_generator` attempts and a final valid query.
- `test_auto_fallback_triggers_on_other_intent`: a question that classifies as `other` routes to the generated path (assert the `strategy` step says `fallback:generated`).
- `test_auto_without_provider_stays_template`: NullProvider → no generated dead-end; honest template failure.

Keep everything offline by injecting the mock provider and monkeypatching the Fuseki client — no network, consistent with the existing suite.

### E. UI + docs

- KGQA Workflow page: add **"Auto (template → generated)"** as the default mode; keep the two explicit modes for demos. Render the `strategy` step prominently.
- Update `docs/kgqa_pipeline.md` to mark the fallback edge as implemented and document the triggers and the repair loop.

## Phasing

1. ✅ **Repair loop** in `generated_sparql_workflow` + prompts + tests (self-contained, no orchestrator yet). *Done:* `repair_user_prompt` (`app/llm/prompts.py`), `repair_sparql` (`app/llm/sparql_generator.py`), a bounded validate→repair loop in `run_generated_sparql_kgqa` (`max_attempts`, per-attempt steps, fail-fast on forbidden writes), and deterministic mock-provider tests (`tests/test_generated_repair.py`).
2. **Auto orchestrator** (`run_kgqa(mode="auto")`) + strategy trace + fallback tests.
3. **UI wiring** (auto mode default) + docs update.
4. **Eval**: run the completed harness in `--mode generated` and `auto` over the competency set; the fallback should lift intent/answer coverage above the template-only `pass_rate=0.2`. Capture before/after numbers.

## Risks / decisions to confirm

- **Cost/latency:** auto-fallback + repair can issue up to ~3 LLM calls per question. Gate the "0 rows → fallback" trigger behind a flag (default on) so it can be disabled for cost-sensitive runs.
- **Loop safety:** hard cap attempts at 2; never retry on policy *writes* (fail fast — a write attempt is not a near-miss).
- **Threshold tuning:** the intent-confidence cutoff for fallback needs a value; derive it from the eval harness rather than guessing.
- **Determinism:** generation uses `temperature=0`, but outputs still vary by provider/model — which is why tests use a mock provider, not a live one.

## Acceptance criteria

- `run_kgqa(mode="auto")` answers a competency question that has no matching template by generating and executing a valid, term-checked SPARQL query.
- With no provider, auto mode behaves exactly like template mode (no regressions, no dead-ends).
- An invalid generated query is repaired within the attempt budget or fails closed with a clear caveat.
- New offline tests cover end-to-end success, the repair loop, and the fallback trigger; the full suite stays green.
- `docs/kgqa_pipeline.md` reflects the implemented fallback; the eval harness shows improved coverage in generated/auto mode over template-only.
