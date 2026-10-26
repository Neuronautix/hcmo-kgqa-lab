# HCMO-KGQA Lab — developer & demo workflow targets
PYTHON ?= python

.PHONY: help install up down fuseki-up build-profile merge reason load \
        validate eval reset demo demo-serve test ui lint sync-hcmo sync-hcmo-dry         hcmo-verify hcmo-check-upstream eval-hcmo

help:
	@echo "HCMO-KGQA Lab targets:"
	@echo "  install        Install package + dev deps (editable)"
	@echo "  up             docker compose up -d (fuseki + ui)"
	@echo "  down           docker compose down"
	@echo "  fuseki-up      Start only the Fuseki service"
	@echo "  build-profile  Build ontology profile/terms/prefixes JSON"
	@echo "  merge          Merge example TTL + ontology into generated KG"
	@echo "  reason         Materialize OWL-RL/RDFS inferences"
	@echo "  load           Load merged KG into Fuseki via GSP"
	@echo "  validate       Run SHACL validation over the KG"
	@echo "  eval           Run the test-question evaluation harness"
	@echo "  reset          Clear generated/ + Fuseki and rebuild"
	@echo "  demo           merge -> reason -> load (presentation pipeline)"
	@echo "  demo-serve     Offline Fuseki-compatible SPARQL endpoint (rdflib, no Docker)"
	@echo "  test           Run the pytest suite"
	@echo "  ui             Launch the Streamlit app locally"
	@echo "  lint           Compile-check scripts"
	@echo "  sync-hcmo      Vendor the HCMO release pinned in sync/hcmo_sources.yaml"
	@echo "  sync-hcmo-dry  Dry-run the pin (fetch + verify + term-diff, no writes)"
	@echo "  hcmo-verify    Offline: check vendored HCMO files against the lockfile"
	@echo "  hcmo-check-upstream  Report whether a newer HCMO release exists"
	@echo "  eval-hcmo      Offline: run upstream CQs + SHACL on the vendored release"

install:
	pip install -e ".[dev]"

up:
	docker compose up -d

down:
	docker compose down

fuseki-up:
	docker compose up -d fuseki

build-profile:
	$(PYTHON) scripts/build_ontology_profile.py

merge:
	$(PYTHON) scripts/merge_rdf_graphs.py

reason:
	$(PYTHON) scripts/materialize_reasoning.py

load:
	$(PYTHON) scripts/load_to_fuseki.py

validate:
	$(PYTHON) scripts/validate_shacl.py

eval:
	$(PYTHON) scripts/run_test_questions.py

reset:
	$(PYTHON) scripts/reset_demo.py

demo: merge reason load
	@echo "Demo pipeline complete: merged, reasoned, and loaded into Fuseki."

demo-serve:
	$(PYTHON) scripts/demo_serve.py

test:
	$(PYTHON) -m pytest tests/ -q

ui:
	streamlit run app/streamlit_app.py

lint:
	$(PYTHON) -m py_compile scripts/*.py

sync-hcmo:
	$(PYTHON) scripts/sync_hcmo.py

sync-hcmo-dry:
	$(PYTHON) scripts/sync_hcmo.py --dry-run

hcmo-verify:
	$(PYTHON) scripts/sync_hcmo.py --verify

hcmo-check-upstream:
	$(PYTHON) scripts/sync_hcmo.py --check-upstream

eval-hcmo:
	$(PYTHON) scripts/eval_hcmo_release.py
