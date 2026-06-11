# HCMO-KGQA Lab — developer & demo workflow targets
PYTHON ?= python

.PHONY: help install up down fuseki-up build-profile merge reason load \
        validate eval reset demo test ui lint sync-hcmo sync-hcmo-dry

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
	@echo "  test           Run the pytest suite"
	@echo "  ui             Launch the Streamlit app locally"
	@echo "  lint           Compile-check scripts"
	@echo "  sync-hcmo      Pull canonical HCMO upstream into vendor/ trees"
	@echo "  sync-hcmo-dry  Dry-run the sync (fetch + term-diff, no writes)"

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
