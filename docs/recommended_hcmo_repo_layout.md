# Recommended layout for the HCMO repository

> **Historical proposal.** The canonical HCMO repository is now
> **https://github.com/dhuzard/HCMO** (it adopted the `hcmo.yaml` release
> manifest described here); the lab pins its releases as described in
> [`hcmo_sync.md`](hcmo_sync.md).

This is a proposal for how to (re)shape the HCMO repository
so that it is clean as a standalone ontology project *and* trivially
consumable by downstream tools such as this `hcmo-kgqa-lab`.

The single most important idea: **the HCMO repo should publish a small,
stable, machine-readable "release contract"** (a manifest + a built
artifact + a profile) so consumers never have to guess file names,
namespaces, or which module to load. Everything else is implementation
detail that consumers should not depend on.

---

## 1. Guiding principles

1. **One canonical IRI, versioned.** Keep the ontology IRI stable
   (`https://w3id.org/hcmo/ontology/hcm#`) and add a `owl:versionIRI` +
   `owl:versionInfo` on every release. Consumers pin by version, not by
   commit.
2. **Author modular, publish merged.** Keep authoring split into modules
   (core, alignments, metadata, bridges) but also publish a single
   **built, merged artifact** so consumers can load one file.
3. **A manifest is the API.** A top-level `hcmo.yaml` (or `dataset.json`)
   declares the namespace, version, module list, the merged artifact path,
   shapes, queries, and examples. Downstream sync code reads *only* the
   manifest and never hardcodes paths.
4. **Ship a profile.** Publish a generated `profile.json` (classes,
   properties, labels, counts) so consumers can do term retrieval / UI
   without parsing OWL themselves.
5. **Releases are immutable.** Tag releases (`v1.0.0`, `v1.1.0`) and attach
   the merged artifact + profile as GitHub Release assets. `main` can move;
   tags don't.

---

## 2. Proposed directory layout

```text
HCMO/
├── README.md
├── LICENSE
├── CITATION.cff
├── CHANGELOG.md
│
├── hcmo.yaml                      # ⭐ the release contract / manifest (see §3)
│
├── ontology/
│   ├── modules/                   # hand-authored, modular
│   │   ├── hcm-core.ttl
│   │   ├── hcm-align.ttl          # external ontology alignments
│   │   ├── hcm-metadata.ttl       # provenance, dcterms, versioning
│   │   └── hcm-bridge-animal.ttl  # bridges to animal/other ontologies
│   ├── imports/                   # vendored/cached external imports (optional)
│   └── context.jsonld             # JSON-LD context for the namespace
│
├── dist/                          # ⭐ GENERATED — built by CI, committed or released
│   ├── hcmo.ttl                   # merged ontology (all modules)
│   ├── hcmo.owl                   # merged, RDF/XML (for OWL tooling)
│   ├── hcmo.json                  # merged, JSON-LD
│   └── profile.json               # classes/properties/labels/counts
│
├── shapes/
│   └── hcm-shapes.ttl             # SHACL — the canonical metadata-quality shapes
│
├── queries/
│   ├── competency_questions.yaml  # id + NL question + description per CQ
│   └── cq-*.rq                     # runnable SPARQL, one per CQ
│
├── examples/
│   ├── abox-minimal.ttl           # smallest valid instance graph
│   └── abox-edge-cases.ttl        # deliberately-imperfect data for SHACL demos
│
├── docs/
│   ├── MODEL.md                   # the conceptual model
│   ├── FIELD-TIERS.md             # mandatory / recommended / optional metadata
│   ├── ALIGNMENTS.md
│   └── ARCHITECTURE.md
│
├── tooling/
│   ├── build.sh                   # modules/ -> dist/ (ROBOT merge + reason)
│   ├── make-profile.py            # dist/hcmo.ttl -> dist/profile.json
│   └── validate.sh                # ROBOT report + pySHACL + SPARQL smoke
│
└── .github/workflows/
    ├── validate.yml               # PR gate: parse, ROBOT report, SHACL, CQ run
    └── release.yml                # on tag: build dist/, attach assets, publish
```

Your current repo is already ~80% of this — the main additions are
`hcmo.yaml` (the manifest), a built `dist/` with a **merged** artifact +
`profile.json`, and `queries/competency_questions.yaml` alongside the
`.rq` files.

---

## 3. The manifest (`hcmo.yaml`) — the contract consumers read

This is the one file `hcmo-kgqa-lab`'s sync layer keys off. Keep its shape
stable even when you reshape everything else.

```yaml
name: HCMO
title: Home Cage Monitoring Ontology
version: 1.0.0
namespace: "https://w3id.org/hcmo/ontology/hcm#"
prefix: hcm
ontology_iri: "https://w3id.org/hcmo/ontology/hcm"
version_iri: "https://w3id.org/hcmo/ontology/hcm/1.0.0"

# Authoring modules (load order matters if reasoning)
modules:
  - ontology/modules/hcm-core.ttl
  - ontology/modules/hcm-align.ttl
  - ontology/modules/hcm-metadata.ttl
  - ontology/modules/hcm-bridge-animal.ttl

# Built artifacts (preferred entry points for consumers)
dist:
  merged_ttl: dist/hcmo.ttl
  merged_owl: dist/hcmo.owl
  jsonld: dist/hcmo.json
  profile: dist/profile.json
  context: ontology/context.jsonld

shapes:
  - shapes/hcm-shapes.ttl

queries:
  index: queries/competency_questions.yaml
  dir: queries/

examples:
  - examples/abox-minimal.ttl
  - examples/abox-edge-cases.ttl
```

With this in place, the lab's `sync/hcmo_sources.yaml` collapses to a
single pointer at `hcmo.yaml`, and re-shaping the HCMO repo (renaming
modules, changing classes) requires **zero changes** in the lab as long as
the manifest stays accurate.

---

## 4. Conventions that make downstream combination painless

- **Every term gets `rdfs:label` + a definition** (`skos:definition` or
  `IAO:0000115`). The lab's term retriever and the LLM grounding rely on
  labels/comments — untyped or unlabeled terms are invisible to KGQA.
- **Mark metadata tiers in the ontology**, not just in docs. e.g. annotate
  properties with `hcm:tier "mandatory"|"recommended"|"optional"` (or use
  the SHACL shapes as the single source of truth for "mandatory"). The lab
  surfaces these as "VCG-readiness".
- **Keep SHACL shapes target-class-driven** (`sh:targetClass`) so they
  travel with the ontology and the lab can run them unchanged.
- **Name competency questions stably** (`CQ001…`) and keep the NL question
  text in `competency_questions.yaml`. The lab maps NL questions →
  templates by these ids.
- **Don't break the namespace.** If you must, bump `owl:versionIRI` and
  list term renames in `CHANGELOG.md` under a `Renamed:` section the lab
  can parse for a migration map.
- **Tag releases.** The lab can then pin `HCMO_REF=v1.1.0` for
  reproducible demos and bump deliberately.

---

## 5. How the two repos combine (current implementation)

```text
HCMO repo (a pinned release tag, e.g. v0.4.1)
   hcmo.yaml ─┐
   dist/hcmo.ttl, dist/profile.json
   shapes/hcm-shapes.ttl
   queries/*.rq, examples/*.ttl
              │  (git clone --depth 1 @ tag; commit SHA + release assets verified)
              ▼
hcmo-kgqa-lab  scripts/sync_hcmo.py  (manifest-driven, no hardcoded terms)
   → ontology/vendor/hcmo/      (merged ontology + profile)
   → shapes/vendor/hcmo/
   → sparql/vendor/hcmo/queries/
   → kg/vendor/hcmo/examples/
   → sync/HCMO_SYNC.lock.json   (tag, commit SHA, sha256 per file, terms)
              │  (flip HCMO_ACTIVE_SOURCE=vendor)
              ▼
   Jena/Fuseki single RDF graph → KGQA / SHACL / reasoning
```

The lab keeps its synthetic demo model as the default and vendors the pinned
release alongside it. To move to a new HCMO release:

1. edit `release_tag` / `commit_sha` / `version` in `sync/hcmo_sources.yaml`
   and run `make sync-hcmo` → vendors the release, prints the **term-diff**
   (added/removed classes & properties) and writes sha256 pins.
2. `make eval-hcmo` and `make test` → the upstream competency questions must
   still return their reviewed answers on the vendored copy.
3. Review the **adaptation surface** checklist in `docs/hcmo_sync.md` and
   record changed answers in a `docs/HCMO_<version>_MIGRATION.md` note.
4. Set `HCMO_ACTIVE_SOURCE=vendor` to switch the lab onto the real HCMO.

The weekly `sync-hcmo.yml` GitHub Action is report-only: it verifies the pins,
re-runs the vendored competency questions and reports (in the job summary)
when a newer upstream release exists. It needs no secrets and never opens PRs.
