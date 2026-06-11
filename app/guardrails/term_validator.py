"""Verify that hcmo:/ex: terms used in a SPARQL query exist in the ontology."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.ontology.loader import load_prefixes
from app.ontology.term_index import TermIndex

# prefixed name like hcmo:Dataset or ex:exp_gait2021
_PREFIXED_RE = re.compile(r"\b([A-Za-z][\w-]*):([A-Za-z][\w-]*)\b")
# full IRI <...>
_IRI_RE = re.compile(r"<([^>]+)>")


def extract_terms(query_text: str, prefixes: Optional[Dict[str, str]] = None) -> List[str]:
    """Return absolute IRIs referenced in the query (prefixed + full)."""
    prefixes = prefixes or load_prefixes()
    iris: List[str] = []
    for full in _IRI_RE.findall(query_text or ""):
        iris.append(full)
    for pfx, local in _PREFIXED_RE.findall(query_text or ""):
        if pfx in prefixes:
            iris.append(prefixes[pfx] + local)
    # de-dup preserving order
    seen, out = set(), []
    for i in iris:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def validate_terms(
    query_text: str,
    index: Optional[TermIndex] = None,
    prefixes: Optional[Dict[str, str]] = None,
) -> Dict[str, List[str]]:
    """Split referenced ontology terms into known / unknown.

    Only ``hcmo:`` terms are checked against the ontology schema; ``ex:`` data
    instances are not part of the schema and are reported as ``data`` (not
    treated as unknown errors).
    """
    prefixes = prefixes or load_prefixes()
    idx = index or TermIndex.load()
    hcmo_ns = prefixes.get("hcmo", "http://w3id.org/hcmo#")
    ex_ns = prefixes.get("ex", "http://example.org/hcmo/data#")

    known: List[str] = []
    unknown: List[str] = []
    data: List[str] = []
    for iri in extract_terms(query_text, prefixes):
        if iri.startswith(ex_ns):
            data.append(iri)
        elif iri.startswith(hcmo_ns):
            if idx.by_iri(iri) is not None:
                known.append(iri)
            else:
                unknown.append(iri)
        # other namespaces (rdf/rdfs/owl/xsd) are ignored as standard vocab
    return {"known": known, "unknown": unknown, "data": data}
