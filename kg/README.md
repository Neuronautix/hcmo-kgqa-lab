# Knowledge Graph Layer

Instance data (the A-Box) for the HCMO KGQA lab.

## `examples/` vs `generated/`

- **`examples/`** — hand-authored, version-controlled Turtle seed data. Each file
  is **self-contained** (declares its own prefixes) and parses standalone with
  rdflib. The files are interconnected through shared `ex:` IRIs:

  | file | contents |
  | ---- | -------- |
  | `example_hcm_datasets.ttl`    | ~4 `hcmo:Dataset` |
  | `example_hcm_experiments.ttl` | ~5 `hcmo:HomeCageExperiment` |
  | `example_animals.ttl`         | ~5 `hcmo:AnimalCohort` |
  | `example_systems.ttl`         | ~3 `hcmo:HomeCageSystem` |
  | `example_metrics.ttl`         | ~6 `hcmo:BehavioralMetric` |

  Two nodes deliberately omit a mandatory field so SHACL validation reports
  violations: `ex:ds_activity2023` (missing `hcmo:identifier`),
  `ex:cohort_incomplete` (missing `hcmo:species` and `hcmo:sampleSize`), and
  `ex:exp_pilot2024` (missing `hcmo:durationDays`).

- **`generated/`** — machine-produced graphs (git-ignored except `.gitkeep`).
  Build scripts in the pipeline layer write the asserted / inferred / merged
  Turtle here.

## Three-graph reasoning strategy

Reasoning is staged across three named graphs so that materialized triples never
silently overwrite source data:

1. **asserted** (`http://example.org/graph/asserted`) — the union of all
   `examples/*.ttl` loaded as-is. The ground truth A-Box.
2. **inferred** (`http://example.org/graph/inferred`) — *only* the new triples a
   reasoner derives from `asserted` + the ontology (e.g. a `hcmo:Dataset` with
   the full VCG metadata being classified as `hcmo:VCGReadyDataset`). Kept
   physically separate so provenance ("asserted vs entailed") is preserved.
3. **merged** — `asserted ∪ inferred`, the graph that competency-question SPARQL
   actually runs against.

This keeps the system ontology-native: a single triple store, separation by
named graph rather than by database.
