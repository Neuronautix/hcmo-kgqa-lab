"""Offline tests for the vendored, pinned HCMO release.

No network. These check that:
  * the pin manifest names a release tag + full commit SHA on dhuzard/HCMO,
  * every vendored file matches the sha256 recorded in the lockfile,
  * the upstream competency questions return exactly their reviewed
    ``expected_answers`` over the vendored release graph + positive examples,
  * the vendored SHACL shapes accept the positive examples and reject the
    negative probes.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("rdflib")
pytest.importorskip("yaml")

from app.evaluation import hcmo_release  # noqa: E402

LOCK = REPO_ROOT / "sync" / "HCMO_SYNC.lock.json"


def _sync_module():
    path = REPO_ROOT / "scripts" / "sync_hcmo.py"
    spec = importlib.util.spec_from_file_location("sync_hcmo_vendor_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def release():
    return hcmo_release.VendoredRelease.load()


def test_pin_is_a_release_tag_and_full_commit(release):
    pin = release.pin
    assert pin["repo_url"] == "https://github.com/dhuzard/HCMO"
    assert re.fullmatch(r"v\d+\.\d+\.\d+", pin["release_tag"])
    assert re.fullmatch(r"[0-9a-f]{40}", pin["commit_sha"])
    assert pin["release_tag"] == f"v{pin['version']}"


def test_lockfile_matches_pin_and_sha256s():
    mod = _sync_module()
    manifest = mod.load_manifest(mod.DEFAULT_MANIFEST)
    problems = mod.verify_lock(manifest, mod.read_lock(LOCK))
    assert problems == []


def test_lockfile_records_sha256_for_every_file():
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["files"]
    for rec in lock["files"]:
        assert re.fullmatch(r"[0-9a-f]{64}", rec["sha256"]), rec


def test_vendored_release_identifies_itself_as_pinned_version(release):
    from rdflib import OWL, URIRef

    g = hcmo_release.ontology_graph(release)
    assert release.release_manifest["version"] == release.pin["version"]
    onto = URIRef(release.release_manifest["ontology_iri"])
    assert str(g.value(onto, OWL.versionIRI)) == release.pin["version_iri"]


def test_upstream_competency_questions_match_reviewed_answers(release):
    results = hcmo_release.run_competency_questions(release)
    assert len(results) >= 12
    failures = {
        r.id: {"error": r.error, "expected": r.expected, "actual": r.actual}
        for r in results if not r.ok
    }
    assert failures == {}


def test_every_vendored_query_is_indexed(release):
    import yaml

    index = yaml.safe_load(release.cq_index_path.read_text(encoding="utf-8"))
    indexed = {Path(q["file"]).name for q in index["questions"]}
    on_disk = {p.name for p in release.cq_index_path.parent.glob("cq-*.rq")}
    assert indexed == on_disk


def test_vendored_shapes_accept_positive_and_reject_negative_examples(release):
    pytest.importorskip("pyshacl")
    results = hcmo_release.run_shacl(release)
    assert any(r.negative for r in results) and any(not r.negative for r in results)
    assert [r.example for r in results if not r.ok] == []
