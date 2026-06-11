# Ontology update workflow

When the HCMO ontology changes, the derived artifacts and the loaded graph must
be regenerated so the rest of the system stays consistent.

## When you edit `ontology/current/hcmo.owl`

1. **Rebuild the profile/terms/prefixes JSON**

   ```bash
   make build-profile
   # -> ontology/profiles/hcmo_profile.json
   #    ontology/profiles/hcmo_terms.json
   #    ontology/profiles/hcmo_prefixes.json
   ```

   These JSON artifacts power deterministic, offline ontology-term retrieval and
   the term-validation guardrail. They must be regenerated whenever classes or
   properties are added, renamed, or removed.

2. **Re-merge and re-reason the KG**

   ```bash
   make merge      # asserted_kg.ttl + merged_kg.ttl
   make reason     # inferred_kg.ttl  + merged_kg.ttl
   ```

   New subclass/subproperty axioms change the materialized closure, so always
   re-run reasoning after touching the schema.

3. **Re-validate**

   ```bash
   make validate
   ```

   Confirm the example data still conforms (or that intended violations remain).

4. **Reload Fuseki**

   ```bash
   make load          # default graph
   # or, for a clean slate including named graphs:
   make reset
   ```

## Checklist

- [ ] `hcmo.owl` parses (`make build-profile` succeeds)
- [ ] The five core classes still appear in `hcmo_terms.json`
      (`hcmo:Dataset`, `hcmo:HomeCageExperiment`, `hcmo:AnimalCohort`,
      `hcmo:HomeCageSystem`, `hcmo:BehavioralMetric`)
- [ ] SPARQL templates in `sparql/templates/` only reference terms that exist
- [ ] SHACL shapes updated for new required properties
- [ ] `make demo` runs end-to-end and `make test` passes

## Conventions

- Namespaces: `hcmo:` = `http://w3id.org/hcmo#`, `ex:` =
  `http://example.org/hcmo/data#`.
- The ontology is authored in Turtle even though the file uses the `.owl`
  extension; the loader handles this transparently.
- Keep class/property `rdfs:label` and `rdfs:comment` populated — retrieval and
  the term index tokenize them for keyword search.
