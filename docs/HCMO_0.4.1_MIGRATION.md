# Migration note: vendored HCMO legacy snapshot → HCMO 0.4.1

This note records what changed when the lab's vendored HCMO moved to the
pinned **HCMO 0.4.1** release, and why. It is the reference for every
evaluation answer that differs from before.

## What was vendored before

| | Before | After |
|---|---|---|
| Source repo | `https://github.com/Neuronautix/HCMO` (now HTTP 404) | `https://github.com/dhuzard/HCMO` |
| Ref | `main`, resolved to commit `2e60566310e7fe0204b4fb261f2395415b197187` (2026-03-09, "Update DOI in CITATION.cff") | tag `v0.4.1`, commit `9503ae4827525d3c82cb0a2cc56a1ce52da39159` |
| Version | legacy term set; `hcm-metadata.ttl` declares `owl:versionIRI <https://w3id.org/hcmo/ontology/hcm/1.0.0>`. HCMO now keeps this under `ontology/legacy/` and says it is not part of any release graph. The lab README and docs informally called it "HCMO 0.1.0". | 0.4.1, `owl:versionIRI <https://w3id.org/hcmo/ontology/hcm/0.4.1>` |
| Ontology files | `ontology/hcm.ttl`, `hcm-align.ttl`, `hcm-metadata.ttl`, `hcm-bridge-animal.ttl` | `dist/hcmo.ttl` (merged release graph, release asset) + `dist/profile.json` + `hcmo.yaml` |
| Pinning | commit SHA + sha256 per file, but tracking `main` | tag + commit SHA (enforced) + sha256 per file; release assets checked byte-identical to the tagged files |
| Competency questions | 5 queries, no expected answers in the lab or upstream | 12 queries + upstream index `competency_questions.yaml` with reviewed `expected_answers` |
| Examples | `abox-minimal.ttl`, `abox-edge-cases.ttl` (legacy terms) | the 5 examples listed in `hcmo.yaml` (3 positive, 2 negative) |
| Auto-sync | weekly workflow opening a PR, which needed "Allow GitHub Actions to create PRs" or a `SYNC_PAT` secret | report-only weekly check (`contents: read`, no secrets). Re-pinning is manual: see `docs/hcmo_sync.md` |

The sha256s of `hcmo.ttl`, `profile.json`, `hcmo.yaml` and
`shapes/hcm-shapes.ttl` match the HCMO 0.4.1 pins used elsewhere in the
ecosystem (metadatapp `api/resources/hcmo/v0.4.1/release.json`).

## Upstream changes that matter here

From the HCMO `CHANGELOG.md` and `ontology/legacy/README.md` at `v0.4.1`:

- **0.0.1 / 0.1.0**: the repository moved from the legacy term set
  (`hcm:System`, `hcm:Animal`, `hcm:livesIn`, `hcm:ObservationWindow`, …) to
  the modular term set (`hcm:MonitoredEnclosure`, `hcm-bio:Subject`,
  `hcm-bio:HousingAssignment`, SOSA observations, …), under the same base
  namespace plus module namespaces `…/hcm/bio#`, `…/env#`, `…/obs#`,
  `…/tech#`. The SHACL shapes, examples, JSON-LD context and competency queries
  were re-authored "around the enclosure → housing assignment → subject
  pattern". Legacy IRIs survive in `hcm-compat` as `owl:deprecated true`,
  with `dcterms:isReplacedBy` only where justified (e.g. `hcm:Animal` →
  `hcm-bio:Subject`, `hcm:captures` → `hcm-tech:captures`). `hcm:System`,
  `hcm:hasEnclosure`, `hcm:livesIn`, `hcm:requiresToThrive`, `hcm:hasSensor`,
  `hcm:extendsEnoughToCapture`, `hcm:durationHours` and
  `hcm:LimitedInteractionWithHumans` are deprecated **without** a replacement.
- **0.3.0**: competency questions are checked against complete reviewed
  answer rows; time-bounded `HousingAssignment` records are authoritative;
  temporal data uses OWL-Time (`time:numericDuration`, `time:unitType`).
- **0.4.1**: multi-animal behaviour (`hcm-bio:InteractingGroup`,
  `hcm-obs:hasInitiator` / `hasRecipient`; ADR-0006, accepted) and the new
  question `social-interaction-partners`. The minimal example gained a second
  mouse and a depth camera.

Term-diff printed by `scripts/sync_hcmo.py` (local names, primary ontology
only; deprecated compat terms count as unchanged): **46 unchanged, 138 added,
22 removed**. The removed names are `AnimalNeedProfile`, `CollectionOfActuators`,
`CollectionOfSensors`, `CommercialSupplier`, `EnvironmentalEnrichment`, `Food`,
`HumanInteractionProfile`, `Laboratory`, `SafetyFromThreat`, `SocialContacts`,
`Water`, `extendsOver`, `hasActuatorComponent`, `hasActuatorSet`,
`hasLimitedHumanInteraction`, `hasPhysicalSpace`, `hasSensorComponent`,
`hasSensorSet`, `indefinitelyExtendable`, `isCapturedOver`,
`limitedHumanInteraction`, `providesNeedProfile`. The full list is in
`sync/HCMO_SYNC.lock.json` (`ontology_terms`).

## Lab evaluation items: no expected answers changed

None of the lab's own evaluation fixtures had an expected answer that changed.
They target the **synthetic** demo ontology (`ontology/current/hcmo.owl`,
`http://w3id.org/hcmo#`), which this change leaves alone:

| Fixture | Items | Changed? |
|---|---|---|
| `app/evaluation/test_questions.yaml` | q1–q6 (expected intents) | No. Results identical before/after |
| `sparql/competency_questions.yaml` | CQ001–CQ005 | No. Results identical before/after |
| `app/evaluation/expected_terms.yaml` | expected synthetic IRIs | No |
| `tests/*` synthetic counts | `test_ontology_profile`, `test_template_queries`, `test_term_validator` | No |

One test assertion changed for a file rename, not an answer:
`tests/test_hcmo_sync.py::test_active_ontology_vendor_flip` now expects the
vendor-mode ontology file to be `hcmo.ttl` (the 0.4.1 merged release asset)
instead of `hcm.ttl` (a legacy module that is no longer in any release).

## Vendored HCMO competency questions: old vs new

Before this change the lab never checked the vendored queries. The "old"
column below is what the legacy queries returned when run on the legacy
vendored ontology + `abox-minimal.ttl` (the lab's previous state). The "new"
column is upstream's **reviewed** `expected_answers` for 0.4.1. The lab now
asserts these in `tests/test_hcmo_vendor.py` and `make eval-hcmo`, and has not
edited them. Example IRIs are shortened: `min:` =
`https://example.org/hcmo/minimal/`, `isa:` =
`https://example.org/hcmo/isa-crate/`, `sub:` =
`https://w3id.org/hcmo/id/example-submission/`, `old:` =
`https://mfg.example.com/hcm/id/`.

| CQ (file) | Old question / pattern | Old answer (legacy) | New question / pattern (0.4.1) | New reviewed answer | Justifying HCMO change |
|---|---|---|---|---|---|
| `cq-animals-by-enclosure.rq` | animals per system enclosure: `hcm:System hcm:hasEnclosure ?e`, `?a a hcm:Animal ; hcm:livesIn ?e` | 1 row: `old:System_A`, `old:Enc_01`, `old:Mouse_1` | "Which biological subjects are assigned to each monitored enclosure?" `hcm:MonitoredEnclosure` ← `hcm-bio:HousingAssignment` ← `hcm-bio:Subject` | 3 rows: `isa:cage-12` → `isa:animal-1`; `min:cage-12` → `min:mouse-1, min:mouse-2`; `sub:enclosure-example-hcm` → `sub:subject-example-hcm` | `Animal` → `hcm-bio:Subject`; `System`/`hasEnclosure`/`livesIn` deprecated; housing assignments authoritative (0.1.0, 0.3.0). The `?system` column is gone. |
| `cq-missing-dimensions.rq` | `hcm:Enclosure` without `hcm:hasDimensions` | 0 rows | same over `hcm:MonitoredEnclosure` | 0 rows | Enclosure hierarchy re-rooted (`MonitoredEnclosure` ⊑ `Enclosure`), `Dimensions` → `EnclosureDimensions` (0.1.0). Answer unchanged. |
| `cq-needs-provisioning.rq` | animals whose need profile (`hcm:requiresToThrive`) lacks food, water, social contacts, safety or enrichment | 0 rows | "Which housed subjects are assigned to enclosures with incomplete husbandry requirements?" The enclosure lacks `hasFoodRequirement`, `hasWaterRequirement`, `hasSafetyRequirement` or `hasEnrichmentRequirement` | 4 rows: `isa:animal-1`@`isa:cage-12`, `min:mouse-1`@`min:cage-12`, `min:mouse-2`@`min:cage-12`, `sub:subject-example-hcm`@`sub:enclosure-example-hcm` | `requiresToThrive`, `AnimalNeedProfile`, `Food`, `Water`, `SocialContacts`, … removed or deprecated. Requirements moved to the enclosure (thrive profile) (0.1.0). **See review item R1.** |
| `cq-sensors-behaviors.rq` | behaviours captured by each system's sensor (`hcm:hasSensor`, `hcm:captures`) | 1 row: `old:System_A`, `old:IR_Sensor_1`, `old:Behav_Rec_1` | "Which properties does each monitored enclosure's sensor capture?" `hcm-tech:monitoredBy`, `hcm-tech:captures` (SOSA observable property) | 5 rows: `isa:cage-12`/`isa:sensor-1`/null; `min:cage-12` with `ir-sensor-1`→`locomotor-activity`, `temperature-sensor-1`→`ambient-temperature`, `depth-camera-1`→`social-behavior`; `sub:enclosure-example-hcm`/`sub:sensor-ir-camera`/null | `hasSensor` deprecated; `captures` → `hcm-tech:captures`; sensors are anchored on SOSA and capture properties, not behaviour records (0.1.0); depth camera added (0.4.1). |
| `cq-systems-24h-limited.rq` | systems whose sensor captures a behaviour over an `ObservationWindow` of ≥ 24 `durationHours` with a `LimitedInteractionWithHumans` property | 1 row: `old:System_A`, `old:TI_24h`, `24.0` | "Which monitored enclosures have behavior observations lasting at least 24 hours under a stated condition?" `hcm-obs:BehaviorObservation` with `sosa:phenomenonTime`, OWL-Time duration ≥ 24 h or ≥ 1 day, and any `hcm-obs:hasCondition` | 1 row: `min:cage-12`, `min:observation-1`, `24.0`, `time:unitHour`, condition `min:limited-human-interaction` | `ObservationWindow`, `durationHours`, `LimitedInteractionWithHumans` deprecated without replacement; OWL-Time temporal model (0.1.0, 0.3.0). **See review item R2.** |
| 7 new CQs: `isa-factor-group-assignment`, `isa-recording-provenance`, `isa-statistical-result-provenance`, `environment-spec-observation`, `current-housing-at-time`, `status-evidence-at-time`, `social-interaction-partners` | did not exist | n/a | see `sparql/vendor/hcmo/queries/competency_questions.yaml` | 1, 1, 1, 1, 1, 1 and 2 rows, all matching upstream | Added in 0.3.0 (ISA/STATO, temporal, status evidence) and 0.4.1 (multi-animal). |

All 12 upstream CQs return exactly the reviewed answers on the vendored copy,
and the vendored shapes accept the 3 positive examples and reject the 2
negative probes (`make eval-hcmo`: 17/17).

## Items needing scientific review

These are not resolved by this change, and nothing here should be read as
scientific validation of them. They need a domain expert or the HCMO
maintainers:

- **R1 (`needs-provisioning`, change in meaning).** The legacy question checked
  an *animal's* need profile and included **social contacts**. The 0.4.1
  question checks the *enclosure's* husbandry requirements (food, water,
  safety, enrichment). Social requirements are now
  `hcm-bio:hasSocialRequirement` on a subject or experimental group, and the
  query does not check them. Also, every housed subject in the reviewed
  examples is returned as incompletely provisioned. A reviewer should confirm
  this is the intended welfare question before the lab presents it as
  "animals whose needs are not met".
- **R2 (`systems-24h-limited`, weaker constraint).** The legacy query
  required the condition to be *typed* as limited human interaction. The 0.4.1
  query accepts **any** stated `hcm-obs:hasCondition`. "Limited human
  interaction" now survives only in the example's instance IRI. The id still
  says "limited", but the question text says "under a stated condition". A
  reviewer should decide whether the lab should add a condition-type filter,
  and if so which term to use, since HCMO 0.4.1 deprecates
  `LimitedInteractionWithHumans` with no replacement.
- **R3 (no replacement for "system").** `hcm:System` is deprecated with no
  `dcterms:isReplacedBy`. Questions that were about *systems* (legacy
  `?system` columns, and the lab's synthetic `HomeCageSystem` / vendor
  questions such as q5 "List all home cage systems and their vendors") now
  have no direct counterpart in the release graph. Systems and vendors are SKOS
  vocabularies under `vocabularies/`, outside the release, and they are not
  vendored. Before switching the lab to `HCMO_ACTIVE_SOURCE=vendor`, someone
  has to decide how the lab's system-level questions map to
  `MonitoredEnclosure` and the SKOS system and vendor schemes.
- **R4 (vendor mode is still untested end to end).** The lab's templates,
  intent heuristics, slot lists, synthetic SHACL shapes and evaluation
  fixtures are written for the synthetic term set (checklist in
  `docs/hcmo_sync.md`). This change does not adapt them, so NL question
  answering over the real HCMO still depends on that adaptation and on review
  of the mapping. The only evaluation of the real ontology in the lab is the
  upstream competency-question and SHACL check above.
