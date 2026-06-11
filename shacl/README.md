# SHACL Layer

Constraint shapes that validate the HCMO knowledge graph and report
VCG-readiness.

## Shapes

| file | targets | enforces |
| ---- | ------- | -------- |
| `hcm_dataset_shape.ttl`      | `hcmo:Dataset`            | `title`, `identifier`, `hasExperiment` (minCount 1) |
| `hcm_experiment_shape.ttl`   | `hcmo:HomeCageExperiment` | `durationDays`, `usesSystem`, `hasCohort`, `measuresMetric` |
| `animal_cohort_shape.ttl`    | `hcmo:AnimalCohort`       | `species`, `strain`, `sampleSize` |
| `hcm_system_shape.ttl`       | `hcmo:HomeCageSystem`     | `systemName`, `vendor` |
| `behavioral_metric_shape.ttl`| `hcmo:BehavioralMetric`   | `metricName`, `metricUnit` |
| `vcg_readiness_shape.ttl`    | `hcmo:Dataset`            | VCG reuse metadata, reported as `sh:Warning` |

All shapes parse with rdflib/pyshacl. Each `sh:property` carries an
`sh:message` so reports are human-readable.

## Expected violations on the seed data

The hand-authored examples include deliberately incomplete nodes so validation
is non-trivial:

- `ex:ds_activity2023` — missing `hcmo:identifier`
  (DatasetShape `sh:Violation`; VCGReadinessShape `sh:Warning`).
- `ex:cohort_incomplete` — missing `hcmo:species` and `hcmo:sampleSize`
  (AnimalCohortShape `sh:Violation`).
- `ex:exp_pilot2024` — missing `hcmo:durationDays`
  (HomeCageExperimentShape `sh:Violation`).

## VCG-readiness reporting

`vcg_readiness_shape.ttl` is a *report*, not a hard gate. It uses SHACL property
paths (e.g. `( hcmo:hasExperiment hcmo:hasCohort hcmo:species )`) to check that
the metadata needed for Virtual Control Group reuse — identifier, duration,
species, strain, sample size — is reachable from each `hcmo:Dataset`. Failures
are emitted at `sh:Warning` severity so a dataset can be valid yet flagged as
"not yet VCG-ready", complementing the reasoner's `hcmo:VCGReadyDataset`
materialization.
