# HCMO Upstream Sync Layer

This lab ships a **synthetic demo ontology** (`hcmo:` namespace, classes such
as `Dataset` / `HomeCageExperiment`) so the KGQA pipeline is fully runnable
offline. The **sync layer** lets the lab additionally *vendor* the canonical
HCMO ontology, SHACL shapes and competency queries from the upstream repo, so
the lab can be switched onto the real HCMO when it is ready — without ever
overwriting the synthetic demo.

## The vendor model

The sync layer **never edits the synthetic demo**. It copies upstream files
into separate `*/vendor/` trees:

| Kind      | Vendored into                          |
|-----------|----------------------------------------|
| ontology  | `ontology/vendor/hcmo/`                |
| context   | `ontology/vendor/hcmo/context.jsonld`  |
| shapes    | `shapes/vendor/hcmo/`                  |
| queries   | `sparql/vendor/hcmo/queries/`         |
| examples  | `kg/vendor/hcmo/examples/`            |

The synthetic assets (`ontology/current/`, `ontology/profiles/`, `shacl/`,
`sparql/templates/`, `kg/examples/`) are untouched.

## The manifest

`sync/hcmo_sources.yaml` is the **single place to edit** when upstream changes.
It is ontology-agnostic — no class names, properties or namespaces are
hardcoded anywhere in the sync code. The manifest holds:

- `repo_url` — the upstream repository,
- `ref` — the git branch/tag/SHA to track (default `main`),
- `primary_ontology` — dest of the main ontology module used for namespace +
  term detection,
- `files` — a list of `{src, dest, kind}` mappings.

When upstream is reshaped (file renames, new modules, namespace change) you
only edit this file and re-run the sync.

## Running a sync

```bash
make sync-hcmo          # fetch + vendor + lockfile + profile + term-diff
make sync-hcmo-dry      # fetch + term-diff only, writes nothing
```

Under the hood (`scripts/sync_hcmo.py`):

1. shallow `git clone --depth 1 --branch <ref>` into a tempdir (falls back to
   `raw.githubusercontent.com` per-file download if git is unavailable),
2. resolves the actual commit SHA,
3. archives the previous vendor tree into `ontology/vendor/_archive/<sha>/`,
4. copies each manifest file into its `dest`,
5. validates every vendored `.ttl`/`.owl` parses with rdflib (non-zero exit on
   failure, unless `--dry-run`),
6. detects the upstream namespace **by parsing** the primary ontology,
7. writes the lockfile and a vendored profile,
8. prints a term-diff report.

Flags: `--ref`, `--repo-url`, `--manifest`, `--no-profile`, `--dry-run`.

## The lockfile

`sync/HCMO_SYNC.lock.json` records the exact synced state for reproducibility:

```
repo_url, ref, commit_sha, synced_at (ISO),
files: [{src, dest, sha256}],
lab_namespace_detected, upstream_namespace_detected,
ontology_terms: {classes[], object_properties[], datatype_properties[]}
```

It is **committed**. The `ontology_terms` block is what the term-diff compares
against on the next sync.

## Reading the term-diff report

On every run the script prints:

```
TERM-DIFF REPORT (vs previous lockfile)
  unchanged: N
  added:     N  [...names...]
  removed:   N  [...names...]
```

`added` / `removed` are owl class + property **local names** that appeared or
disappeared between the previously-locked HCMO and the freshly-fetched one.
This is your exact change surface when a new HCMO lands: a removed class likely
breaks a SHACL shape or a SPARQL template; an added class may be worth
modelling.

## Tracking `main` vs pinning a ref

- **Track main** (default): leave `ref: main` in the manifest. The weekly CI
  workflow re-syncs and opens a PR when anything changes.
- **Pin a release**: set `ref:` to a tag or commit SHA in the manifest (or pass
  `--ref`). The resolved `commit_sha` is always written to the lockfile
  regardless, so the synced state is reproducible either way.

## Switching the lab onto the real HCMO

The active ontology is controlled by **one env flag**, `HCMO_ACTIVE_SOURCE`:

- `synthetic` (default) — the lab uses the bundled synthetic demo ontology.
  `Settings.active_ontology_path == ontology_path`. Nothing changes.
- `vendor` — `Settings.active_ontology_path` points at the vendored upstream
  primary module (`ontology/vendor/hcmo/hcm.ttl`).

```bash
make sync-hcmo
export HCMO_ACTIVE_SOURCE=vendor   # or set it in .env
```

Note `active_ontology_path` is additive: the existing `ontology_path` default
is unchanged, so nothing breaks until you intentionally flip the flag.

## CI automation

`.github/workflows/sync-hcmo.yml` runs weekly (and on `workflow_dispatch`),
installs minimal deps, runs the sync, and — if there is a git diff — opens a PR
titled `chore: sync HCMO upstream` whose body embeds the term-diff summary. If
nothing changed, it does nothing.

---

## ADAPTATION SURFACE checklist

When you flip onto the real (or reshaped) HCMO, these are the places in the lab
that **hardcode ontology terms / namespaces / prefixes** and must be reviewed.
The sync layer deliberately does **not** auto-edit them — they are demo-shaped.

- [ ] **Namespace / prefixes**
  - `ontology/profiles/hcmo_prefixes.json` — synthetic `hcmo:` =
    `http://w3id.org/hcmo#` (upstream is `https://w3id.org/hcmo/ontology/hcm#`).
  - `app/ontology/loader.py` — `DEFAULT_PREFIXES` fallback map.
- [ ] **Ontology profile artifacts**
  - `ontology/profiles/hcmo_profile.json`, `hcmo_terms.json` — rebuild with
    `scripts/build_ontology_profile.py` against the vendored ontology.
- [ ] **SHACL shapes** — `shacl/*.ttl` target synthetic classes
  (`hcm_dataset_shape.ttl`, `hcm_experiment_shape.ttl`, `hcm_system_shape.ttl`,
  `animal_cohort_shape.ttl`, `behavioral_metric_shape.ttl`,
  `vcg_readiness_shape.ttl`). Compare with vendored `shapes/vendor/hcmo/`.
- [ ] **Jinja SPARQL templates** — `sparql/templates/*.jinja.rq`
  (`compare_experiments`, `find_comparable_datasets`, `list_metrics`,
  `missing_metadata`, `vcg_readiness`).
- [ ] **Embedded SPARQL templates** — `app/workflows/templates.py`
  (`PREFIXES` block + per-intent queries using `hcmo:HomeCageExperiment`,
  `hcmo:usesSystem`, `hcmo:hasDataset`, …).
- [ ] **Heuristic intent / term mappings**
  - `app/llm/intent_classifier.py` — `_HEURISTICS` cue lists.
  - `app/llm/slot_extractor.py` — `_SPECIES`, `_STRAINS`, `_SYSTEMS`,
    `_METRICS` keyword lists.
- [ ] **Evaluation fixtures** — `app/evaluation/expected_terms.yaml`,
  `app/evaluation/test_questions.yaml`, `sparql/competency_questions.yaml`.
- [ ] **Expected counts in tests** — `tests/test_ontology_profile.py`,
  `tests/test_template_queries.py`, `tests/test_term_validator.py` assert
  against the synthetic term set.

Use the term-diff report from each sync to prioritise which of these to touch.
