# SPARQL Layer

Competency questions and the queries that answer them.

## Competency questions

`competency_questions.yaml` is the source of truth: five competency questions
(CQ001–CQ005), each with an `id`, natural-language `question`, `description`,
`template` name and `example` filename.

| id | theme | template |
| -- | ----- | -------- |
| CQ001 | comparable datasets (same species + strain) | `find_comparable_datasets` |
| CQ002 | missing mandatory metadata                  | `missing_metadata` |
| CQ003 | metrics measured for a dataset              | `list_metrics` |
| CQ004 | compare two experiments                     | `compare_experiments` |
| CQ005 | VCG-ready candidate datasets                | `vcg_readiness` |

## `examples/` vs `templates/`

- **`examples/*.rq`** — concrete, runnable SPARQL with literal IRIs from the
  seed data. They parse with `rdflib.plugins.sparql.prepareQuery` and execute
  against `kg/examples`. Use them as fixtures and smoke tests.
- **`templates/*.jinja.rq`** — Jinja2-parameterized versions. Each file starts
  with a comment header listing its required slot variables (e.g.
  `dataset_iri`, `class_iri`, `min_sample_size`). After rendering, the output is
  a valid SPARQL query.

## Template-first KGQA

The system answers questions by **selecting a template and filling slots**, not
by free-form query generation. An incoming question is matched to a competency
question / template, the term retriever resolves the entities into IRIs, those
IRIs fill the Jinja slots, and the rendered query runs against the merged graph.
This keeps generated SPARQL grounded in the ontology and reproducible.
