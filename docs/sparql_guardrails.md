# SPARQL guardrails

Because questions can drive LLM-generated SPARQL against a live store, every
query passes a layered set of guardrails in `app.guardrails`. The guarantees
hold for both template-filled and LLM-generated queries.

## 1. Read-only policy (`sparql_policy.validate_sparql`)

The backend is query-only. The policy **rejects** any mutating or remote-loading
operation:

- `INSERT`, `INSERT DATA`, `DELETE`, `DELETE WHERE`
- `DROP`, `CLEAR`, `CREATE`, `LOAD`, `ADD`, `MOVE`, `COPY`
- SPARQL UPDATE in general

It **accepts** `SELECT` and `ASK`, and **requires a `LIMIT`** on result-bearing
queries (auto-injecting or flagging an unbounded `SELECT`) so a single question
cannot exhaust the store.

```text
validate_sparql("INSERT DATA { ... }")   -> rejected
validate_sparql("SELECT ?d WHERE {...} LIMIT 10") -> accepted
validate_sparql("SELECT ?d WHERE {...}") -> flagged / LIMIT-injected
```

## 2. Term validation (`term_validator`)

Every `hcmo:`/`ex:` IRI referenced in a query must exist in the ontology (as
captured in `hcmo_terms.json`). Unknown terms — typos or hallucinated
predicates from the LLM path — are flagged before execution. This is the
mechanism that keeps generated SPARQL ontology-native.

```text
... ?d a hcmo:Dataset ...          -> ok (known class)
... ?d a hcmo:NotARealClassXYZ ... -> flagged (unknown term)
```

## 3. Injection filter (`injection_filter`)

Natural-language input and any retrieved text are screened for prompt-injection
patterns ("ignore previous instructions", attempts to change system role,
attempts to smuggle UPDATE operations, etc.) before reaching the LLM or the
query builder.

## 4. Grounding check (`grounding_checker`)

Before an answer is shown, the grounding checker confirms the answer is
supported by the returned rows. When there are no rows, the system emits an
honest "no results" answer and marks it grounded — it never fabricates entities
or values absent from the graph.

## Ordering

```
question --> injection_filter --> intent/slots --> SPARQL build
          --> sparql_policy + term_validator --> execute --> grounding_checker --> answer
```

A failure at any guardrail stops the pipeline with an explanatory issue rather
than silently producing an unsafe or ungrounded result.
