# SHACL validation & VCG-readiness

SHACL shapes in `shacl/*.ttl` constrain HCMO data so that datasets carry the
metadata needed for downstream reuse — in particular **Virtual Control Group
(VCG) readiness**. Validation runs over the same RDF graph the system queries,
keeping data quality and answering aligned.

## Shapes

| Shape file                     | Targets                    | Checks (representative)                |
|--------------------------------|----------------------------|----------------------------------------|
| `hcm_dataset_shape.ttl`        | `hcmo:Dataset`             | title, identifier, linked experiment   |
| `hcm_experiment_shape.ttl`     | `hcmo:HomeCageExperiment`  | system, cohort, duration               |
| `hcm_system_shape.ttl`         | `hcmo:HomeCageSystem`      | system name, vendor                    |
| `animal_cohort_shape.ttl`      | `hcmo:AnimalCohort`        | species, strain, sample size           |
| `behavioral_metric_shape.ttl`  | `hcmo:BehavioralMetric`    | metric name, unit                      |
| `vcg_readiness_shape.ttl`      | VCG-candidate datasets     | the full metadata set required for VCG |

## Running validation

```bash
# default: validate kg/generated/merged_kg.ttl against shacl/
make validate

# choose a graph and fail the process on non-conformance
python scripts/validate_shacl.py --graph merged --strict
python scripts/validate_shacl.py --graph asserted
python scripts/validate_shacl.py --graph /path/to/data.ttl
```

The backend entry point is `app.shacl.validator.run_validation(data_graph,
shapes_dir=..., ont_graph=..., inference="rdfs")`, which returns a
`ShaclReport` (`conforms`, structured `violations`, raw `text`).

## VCG-readiness

A dataset is **VCG-ready** when it carries the complete metadata required to be
reused as a virtual control group: experiment linkage, system + vendor, cohort
species/strain/sample size, experiment duration, and named behavioral metrics
with units. `vcg_readiness_shape.ttl` encodes these requirements, and
`app.shacl.readiness` summarizes which datasets pass.

The shipped `kg/examples/` data deliberately includes both complete and
incomplete records so the validation page demonstrates real violations as well
as conformance.

## Interpreting results

- **conforms = true** — every targeted node satisfies its shape.
- **violations** — each carries a focus node, the failing constraint, and a
  message (parsed by `app.shacl.report_parser`).
- Validation uses `inference="rdfs"` by default so that subclass/subproperty
  entailments are considered without pre-materializing them.
