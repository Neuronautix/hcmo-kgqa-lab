# Ontology Layer

This directory holds the **semantic backbone** of the HCMO KGQA lab.

## Contents

- `current/hcmo.owl` — the Home Cage Monitoring Ontology in Turtle syntax (`.owl`
  extension). Defines the core classes, object properties and datatype properties,
  with `rdfs:label`/`rdfs:comment` annotations, domains/ranges, a subclass
  (`hcmo:VCGReadyDataset rdfs:subClassOf hcmo:Dataset`) and an `owl:Restriction`
  based `owl:equivalentClass` axiom that lets a reasoner **materialize**
  VCG-ready datasets.
- `profiles/hcmo_prefixes.json` — canonical prefix → namespace map.
- `profiles/hcmo_terms.json` — flat list of every term (`iri`, `label`, `type`,
  `comment`) consumed by the term retriever.
- `profiles/hcmo_profile.json` — summary of classes / properties / counts /
  namespaces.

> The `profiles/*.json` files are seed versions. `scripts/build_ontology_profile.py`
> (other layer) regenerates them directly from `current/hcmo.owl`.

## Namespaces

| prefix | IRI |
| ------ | --- |
| `hcmo:` | `http://w3id.org/hcmo#` |
| `ex:`   | `http://example.org/hcmo/data#` |

## Single-graph design principle

The ontology (T-Box) and the instance data (A-Box) live in **one RDF model**.
There is no separate "schema database" vs "data database": classes, properties
and individuals are all first-class triples queryable with the same SPARQL
engine. This keeps the system *ontology-native* — competency questions, SHACL
shapes and the reasoner all operate over the same triples. Physical separation
is expressed only through **named graphs**
(`http://example.org/graph/asserted` and `http://example.org/graph/inferred`),
not through separate stores.
