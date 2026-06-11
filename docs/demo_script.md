# Demo script

A 10-minute click-through for presenting HCMO-KGQA. It tells one story: *the
ontology is the source of truth, and a single RDF graph powers exploration,
validation, querying, and grounded QA — with no property-graph mirror.*

## 0. Setup (before the talk)

```bash
cp .env.example .env       # set an LLM provider if you want NL answers
docker compose up -d       # Fuseki + Streamlit
make demo                  # merge -> reason -> load
open http://localhost:8501
```

Sanity check: `make test` passes; `make validate` shows the expected mix of
conformance and intended violations.

## 1. Framing (1 min)

- "HCMO-KGQA answers questions about Home Cage Monitoring datasets."
- Key message: **one RDF backend (Apache Jena/Fuseki), no Neo4j/Cypher.** The
  HCMO OWL ontology defines every term we query, validate, and reason over.

## 2. Ontology Explorer (2 min)

- Open the **Ontology Explorer** page.
- Show the five core classes: `Dataset`, `HomeCageExperiment`, `AnimalCohort`,
  `HomeCageSystem`, `BehavioralMetric`.
- Search a term (e.g. "metric") to show the deterministic term index that later
  grounds questions.

## 3. KG Loader (1 min)

- Open **KG Loader**; show the merged graph loaded into Fuseki.
- Mention the pipeline: `merge -> reason -> load`, and the asserted/inferred
  named graphs.

## 4. SHACL Validation (2 min)

- Open **SHACL Validation**; run it over the example data.
- Point out a **VCG-readiness** violation on an intentionally incomplete
  dataset, then a conforming dataset.
- Message: data quality is checked against the same graph we answer from.

## 5. SPARQL Playground (1 min)

- Open **SPARQL Playground**; run one competency-question query, e.g.
  "list metrics for a dataset".
- Try a write query (`INSERT DATA ...`) to show the **read-only guardrail**
  rejecting it.

## 6. KGQA Workflow — the centerpiece (3 min)

- Open **KGQA Workflow**.
- Ask: *"Which datasets use the IntelliCage system?"*
  - Walk the visible pipeline steps: term retrieval -> intent/slots ->
    template-first SPARQL -> guardrails -> execution -> grounded answer.
- Ask a question with no matching data, e.g. *"Which datasets measure heart
  rate?"*
  - Show the **honest grounded answer**: it says there are no results instead of
    inventing one.

## 7. Wrap-up (30 s)

- Recap the single-graph principle and the guardrails.
- Note extensibility: add a competency question -> add a template -> it is
  immediately guarded, validated, and answerable.

## Backup talking points

- *Why no property graph?* The ontology stays the single source of truth;
  SPARQL/SHACL/OWL are W3C standards and interoperate with the wider semantic
  ecosystem.
- *What runs without an LLM?* Everything except free-text intent handling and
  answer phrasing — templates and guardrails are fully deterministic.
