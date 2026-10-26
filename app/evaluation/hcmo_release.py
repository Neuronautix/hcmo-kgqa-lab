"""Offline evaluation of the vendored (pinned) HCMO release.

The upstream HCMO release ships a competency-question index
(``queries/competency_questions.yaml``) whose ``expected_answers`` are the
complete, reviewed answer rows. Upstream computes them over the release graph
plus the positive example A-boxes listed in its ``hcmo.yaml``. This module
re-runs exactly that check against the files vendored into the lab, so the lab
can prove its pinned copy answers the reviewed questions correctly.

It also runs the vendored SHACL shapes against each vendored example (positive
examples must conform, negative probes must not), mirroring upstream.

Nothing here is ontology-specific: all paths come from the lab's pin manifest
(``sync/hcmo_sources.yaml``) and the vendored release manifest (``hcmo.yaml``).
No network access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
PIN_MANIFEST = REPO_ROOT / "sync" / "hcmo_sources.yaml"


def _yaml(path: Path) -> Dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def is_negative_example(path: str) -> bool:
    """Upstream convention: examples named *edge* or *invalid* are negative."""
    return any(tok in Path(path).name.lower() for tok in ("edge", "invalid"))


@dataclass
class VendoredRelease:
    """Resolved locations of the vendored release files."""

    pin: Dict[str, Any]
    src_to_dest: Dict[str, Path]
    release_manifest: Dict[str, Any]

    @classmethod
    def load(cls, pin_manifest: Path = PIN_MANIFEST) -> "VendoredRelease":
        pin = _yaml(pin_manifest)
        src_to_dest = {str(e["src"]): REPO_ROOT / e["dest"] for e in pin["files"]}
        rm_dest = next(
            (REPO_ROOT / e["dest"] for e in pin["files"] if e.get("kind") == "manifest"),
            None,
        )
        release_manifest = _yaml(rm_dest) if rm_dest and rm_dest.exists() else {}
        return cls(pin=pin, src_to_dest=src_to_dest, release_manifest=release_manifest)

    def dest(self, upstream_path: str) -> Path:
        if upstream_path not in self.src_to_dest:
            raise KeyError(f"{upstream_path} is not vendored (add it to sync/hcmo_sources.yaml)")
        return self.src_to_dest[upstream_path]

    @property
    def ontology_path(self) -> Path:
        return REPO_ROOT / self.pin["primary_ontology"]

    @property
    def examples(self) -> List[str]:
        return list(self.release_manifest.get("examples", []))

    @property
    def positive_examples(self) -> List[str]:
        return [e for e in self.examples if not is_negative_example(e)]

    @property
    def cq_index_path(self) -> Path:
        return self.dest(self.release_manifest["queries"]["index"])

    @property
    def shapes_path(self) -> Path:
        return self.dest(self.release_manifest["shapes"])


def ontology_graph(rel: VendoredRelease):
    from rdflib import Graph

    return Graph().parse(str(rel.ontology_path), format="turtle")


def evaluation_graph(rel: VendoredRelease):
    """Release graph + positive examples (the upstream CQ evaluation graph)."""
    g = ontology_graph(rel)
    for ex in rel.positive_examples:
        g.parse(str(rel.dest(ex)), format="turtle")
    return g


def canonical_rows(result) -> List[Dict[str, Optional[str]]]:
    """Rows as {var: str|None}, sorted — same canonical form as upstream."""
    variables = [str(v) for v in result.vars]
    rows = [
        {v: None if row[i] is None else str(row[i]) for i, v in enumerate(variables)}
        for row in result
    ]
    return sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))


@dataclass
class CQResult:
    id: str
    question: str
    file: str
    expected: List[Dict[str, Any]]
    actual: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.actual == self.expected


def run_competency_questions(rel: Optional[VendoredRelease] = None) -> List[CQResult]:
    rel = rel or VendoredRelease.load()
    graph = evaluation_graph(rel)
    index = _yaml(rel.cq_index_path)
    results: List[CQResult] = []
    for q in index.get("questions", []):
        expected = sorted(q.get("expected_answers") or [], key=lambda r: json.dumps(r, sort_keys=True))
        res = CQResult(id=q["id"], question=q.get("question", ""), file=q["file"], expected=expected)
        try:
            text = rel.dest(q["file"]).read_text(encoding="utf-8")
            res.actual = canonical_rows(graph.query(text))
        except Exception as exc:  # noqa: BLE001
            res.error = str(exc)
        results.append(res)
    return results


@dataclass
class ShaclResult:
    example: str
    negative: bool
    conforms: bool

    @property
    def ok(self) -> bool:
        return self.conforms is not self.negative


def run_shacl(rel: Optional[VendoredRelease] = None) -> List[ShaclResult]:
    from pyshacl import validate
    from rdflib import Graph

    rel = rel or VendoredRelease.load()
    shapes = Graph().parse(str(rel.shapes_path), format="turtle")
    ont = ontology_graph(rel)
    out: List[ShaclResult] = []
    for ex in rel.examples:
        data = Graph().parse(str(rel.dest(ex)), format="turtle")
        conforms, _, _ = validate(
            data, shacl_graph=shapes, ont_graph=ont, inference="rdfs",
            abort_on_first=False, do_owl_imports=False,
        )
        out.append(ShaclResult(example=ex, negative=is_negative_example(ex), conforms=bool(conforms)))
    return out
