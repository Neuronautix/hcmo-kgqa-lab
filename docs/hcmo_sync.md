# HCMO Upstream Pin Layer

This lab ships a **synthetic demo ontology** (`hcmo:` namespace, classes such
as `Dataset` / `HomeCageExperiment`) so the KGQA pipeline is fully runnable
offline. The **pin layer** additionally *vendors* a pinned release of the
canonical HCMO ontology, SHACL shapes, competency questions and example
A-boxes from **https://github.com/dhuzard/HCMO**, so the lab can be switched
onto the real HCMO without ever overwriting the synthetic demo.

Current pin: **HCMO 0.4.1**, tag `v0.4.1`, commit
`9503ae4827525d3c82cb0a2cc56a1ce52da39159`, ontology IRI
`https://w3id.org/hcmo/ontology/hcm`, version IRI
`https://w3id.org/hcmo/ontology/hcm/0.4.1`. See
[`HCMO_0.4.1_MIGRATION.md`](HCMO_0.4.1_MIGRATION.md) for what changed relative
to the previously vendored legacy files.

## The vendor model

The pin layer **never edits the synthetic demo**. It copies upstream files
into separate `*/vendor/hcmo/` trees:

| Kind     | Upstream path (v0.4.1)                                  | Vendored into                         |
|----------|---------------------------------------------------------|---------------------------------------|
| ontology | `dist/hcmo.ttl` (release asset)                         | `ontology/vendor/hcmo/hcmo.ttl`       |
| profile  | `dist/profile.json` (release asset)                     | `ontology/vendor/hcmo/profile.json`   |
| manifest | `hcmo.yaml` (release asset)                             | `ontology/vendor/hcmo/hcmo.yaml`      |
| context  | `ontology/context.jsonld`                               | `ontology/vendor/hcmo/context.jsonld` |
| shapes   | `shapes/hcm-shapes.ttl`                                 | `shapes/vendor/hcmo/hcm-shapes.ttl`   |
| queries  | `queries/competency_questions.yaml`, `queries/cq-*.rq`  | `sparql/vendor/hcmo/queries/`         |
| examples | `examples/*.ttl` listed in `hcmo.yaml`                  | `kg/vendor/hcmo/examples/`            |

The synthetic assets (`ontology/current/`, `ontology/profiles/`, `shacl/`,
`sparql/templates/`, `kg/examples/`) are untouched.

Vendored files are stored byte-for-byte (`.gitattributes` disables line-ending
conversion for the vendor trees) so their sha256s hold on every platform.

## The manifest

`sync/hcmo_sources.yaml` is the **single place to edit** when moving to a new
release. It is ontology-agnostic: no class names, properties or namespaces are
hardcoded in the pin code. It holds:

- `repo_url`: `https://github.com/dhuzard/HCMO`,
- `release_tag` + `commit_sha`: the pin. The script refuses to vendor if the
  tag does not resolve to that commit,
- `version`, `version_iri`, `concept_doi`: recorded in the lockfile,
- `primary_ontology`: dest of the merged release graph (namespace + term
  detection, `HCMO_ACTIVE_SOURCE=vendor`),
- `files`: `{src, dest, kind[, release_asset]}` mappings. Files with a
  `release_asset` are also downloaded from the GitHub release and must be
  byte-identical to the tagged file.

## Commands (no secrets, no tokens)

```bash
make sync-hcmo            # fetch tag, verify commit + release assets, vendor, lockfile, term-diff
make sync-hcmo-dry        # same checks + term-diff, writes nothing
make hcmo-verify          # OFFLINE: vendored files vs lockfile sha256s
make hcmo-check-upstream  # report whether a newer upstream release exists
make eval-hcmo            # OFFLINE: upstream CQs + SHACL on the vendored release
```

`scripts/sync_hcmo.py` (default mode):

1. shallow `git clone --depth 1 --branch <release_tag>` with
   `core.autocrlf=false` (exact upstream bytes),
2. checks the resolved commit equals `commit_sha`,
3. downloads each `release_asset` and checks it equals the tagged file,
4. archives (best effort, untracked `ontology/vendor/_archive/`) and clears the
   previous vendor trees, then copies each manifest file into its `dest`,
5. validates every vendored `.ttl` parses with rdflib,
6. detects the upstream namespace **by parsing** the primary ontology (the
   `owl:Ontology` carrying an `owl:versionIRI`),
7. writes the lockfile and prints a term-diff report.

## The lockfile

`sync/HCMO_SYNC.lock.json` records the exact vendored state:

```
repo_url, release_tag (also as ref), commit_sha, version, version_iri,
concept_doi, synced_at (ISO),
files: [{src, dest, sha256[, release_asset]}],
lab_namespace_detected, upstream_namespace_detected,
ontology_terms: {classes[], object_properties[], datatype_properties[]}
```

It is **committed**. `tests/test_hcmo_vendor.py` and `make hcmo-verify` check
every vendored file against it. The `ontology_terms` block is what the
term-diff compares against on the next pin.

## Evaluating the vendored release

HCMO releases ship `queries/competency_questions.yaml`, whose
`expected_answers` are the complete reviewed answer rows, computed upstream
over the release graph plus the positive examples listed in `hcmo.yaml`
(examples named `*edge*` / `*invalid*` are negative SHACL probes).
`app/evaluation/hcmo_release.py` re-runs exactly that on the vendored copy
(`make eval-hcmo`, and `tests/test_hcmo_vendor.py`). The lab never edits the
expected answers: they are upstream's reviewed values.

## Moving to a new HCMO release

Manual and human-reviewed by design:

1. `make hcmo-check-upstream` shows the latest upstream release tag.
2. Read the release notes / `CHANGELOG.md`; edit `release_tag`,
   `commit_sha`, `version`, `version_iri` in `sync/hcmo_sources.yaml`, and the
   `files` list if `hcmo.yaml` lists new examples, shapes or queries.
3. `make sync-hcmo` and review the term-diff.
4. `make eval-hcmo && make test`.
5. Write `docs/HCMO_<version>_MIGRATION.md`: for every competency question or
   lab evaluation item whose answer changed, record old vs new and the HCMO
   change that justifies it; flag anything needing scientific review.
6. Open a PR.

## Reading the term-diff report

```
TERM-DIFF REPORT (vs previous lockfile)
  unchanged: N
  added:     N  [...names...]
  removed:   N  [...names...]
```

`added` / `removed` are owl class + property **local names** that appeared or
disappeared between the previously-locked HCMO and the freshly-fetched one.
HCMO keeps superseded terms as `owl:deprecated` declarations in its
`hcm-compat` module, so a deprecated term still counts as "unchanged" here;
check `owl:deprecated` / `dcterms:isReplacedBy` in the vendored graph.

## Switching the lab onto the real HCMO

The active ontology is controlled by **one env flag**, `HCMO_ACTIVE_SOURCE`:

- `synthetic` (default): the lab uses the bundled synthetic demo ontology.
  `Settings.active_ontology_path == ontology_path`. Nothing changes.
- `vendor`: `Settings.active_ontology_path` points at the vendored merged
  release graph (`ontology/vendor/hcmo/hcmo.ttl`).

`active_ontology_path` is additive and is not yet consumed by the KGQA
templates, which are written against the synthetic term set (see the
checklist below).

## CI automation

`.github/workflows/sync-hcmo.yml` runs weekly, on `workflow_dispatch` and on
PRs touching the pin. It is **report-only** with `contents: read`: it verifies
the sha256 pins, runs `scripts/eval_hcmo_release.py` (fails if the vendored
copy no longer answers the reviewed questions) and writes an upstream-drift
note to the job summary. It needs **no secrets or PATs** and never opens PRs or
pushes; adopting a new release is the manual procedure above.

---

## ADAPTATION SURFACE checklist

When you flip onto the real HCMO, these are the places in the lab that
**hardcode ontology terms / namespaces / prefixes** and must be reviewed.
The pin layer deliberately does **not** auto-edit them: they are demo-shaped.

- [ ] **Namespace / prefixes**
  - `ontology/profiles/hcmo_prefixes.json`: synthetic `hcmo:` =
    `http://w3id.org/hcmo#` (upstream core is
    `https://w3id.org/hcmo/ontology/hcm#`, with modules `hcm-bio:`,
    `hcm-env:`, `hcm-obs:`, `hcm-tech:` under
    `https://w3id.org/hcmo/ontology/hcm/{bio,env,obs,tech}#`).
  - `app/ontology/loader.py`: `DEFAULT_PREFIXES` fallback map.
- [ ] **Ontology profile artifacts**
  - `ontology/profiles/hcmo_profile.json`, `hcmo_terms.json`: rebuild with
    `scripts/build_ontology_profile.py` against the vendored ontology.
- [ ] **SHACL shapes**: `shacl/*.ttl` target synthetic classes
  (`hcm_dataset_shape.ttl`, `hcm_experiment_shape.ttl`, `hcm_system_shape.ttl`,
  `animal_cohort_shape.ttl`, `behavioral_metric_shape.ttl`,
  `vcg_readiness_shape.ttl`). Compare with vendored `shapes/vendor/hcmo/`.
- [ ] **Jinja SPARQL templates**: `sparql/templates/*.jinja.rq`
  (`compare_experiments`, `find_comparable_datasets`, `list_metrics`,
  `missing_metadata`, `vcg_readiness`).
- [ ] **Embedded SPARQL templates**: `app/workflows/templates.py`
  (`PREFIXES` block + per-intent queries using `hcmo:HomeCageExperiment`,
  `hcmo:usesSystem`, `hcmo:hasDataset`, …).
- [ ] **Heuristic intent / term mappings**
  - `app/llm/intent_classifier.py`: `_HEURISTICS` cue lists.
  - `app/llm/slot_extractor.py`: `_SPECIES`, `_STRAINS`, `_SYSTEMS`,
    `_METRICS` keyword lists.
- [ ] **Evaluation fixtures**: `app/evaluation/expected_terms.yaml`,
  `app/evaluation/test_questions.yaml`, `sparql/competency_questions.yaml`.
- [ ] **Expected counts in tests**: `tests/test_ontology_profile.py`,
  `tests/test_template_queries.py`, `tests/test_term_validator.py` assert
  against the synthetic term set.

Use the term-diff report from each pin to prioritise which of these to touch.
