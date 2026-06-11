"""Offline tests for the HCMO sync layer.

These tests MUST NOT hit the network. They exercise the manifest, the helper
functions in scripts/sync_hcmo.py (manifest parsing, namespace/term detection,
term-diff, lockfile schema) against tiny in-memory/temp fixtures, and verify
the new config fields.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MANIFEST = REPO_ROOT / "sync" / "hcmo_sources.yaml"


def _load_sync_module():
    """Import scripts/sync_hcmo.py as a module (skip if deps missing)."""
    pytest.importorskip("rdflib")
    pytest.importorskip("yaml")
    path = REPO_ROOT / "scripts" / "sync_hcmo.py"
    spec = importlib.util.spec_from_file_location("sync_hcmo_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


FIXTURE_TTL = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix ex:  <https://example.org/test/ont#> .

ex: a owl:Ontology .
ex:Animal a owl:Class .
ex:Enclosure a owl:Class .
ex:livesIn a owl:ObjectProperty .
ex:weightGrams a owl:DatatypeProperty .
"""


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------
def test_manifest_loads_and_has_required_keys():
    mod = _load_sync_module()
    data = mod.load_manifest(MANIFEST)
    assert data["repo_url"]
    assert data["ref"]
    assert isinstance(data["files"], list) and data["files"]
    for entry in data["files"]:
        assert "src" in entry and "dest" in entry
        # vendored files must land under a vendor/ tree (never overwrite demo)
        assert "vendor" in entry["dest"]


def test_primary_ontology_resolves():
    mod = _load_sync_module()
    data = mod.load_manifest(MANIFEST)
    prim = mod.primary_ontology_dest(data)
    assert prim is not None
    assert any(str(e["dest"]) == prim for e in data["files"])


def test_load_manifest_rejects_missing_keys(tmp_path):
    mod = _load_sync_module()
    bad = tmp_path / "bad.yaml"
    bad.write_text("repo_url: x\n", encoding="utf-8")
    with pytest.raises(Exception):
        mod.load_manifest(bad)


# --------------------------------------------------------------------------
# Namespace + term detection (offline, temp fixture ontology)
# --------------------------------------------------------------------------
def test_detect_namespace_and_terms(tmp_path):
    mod = _load_sync_module()
    ont = tmp_path / "ont.ttl"
    ont.write_text(FIXTURE_TTL, encoding="utf-8")

    ns = mod.detect_namespace(ont)
    assert ns and "example.org/test/ont" in ns

    terms = mod.collect_terms(ont)
    assert set(terms["classes"]) == {"Animal", "Enclosure"}
    assert terms["object_properties"] == ["livesIn"]
    assert terms["datatype_properties"] == ["weightGrams"]


def test_validate_vendored_detects_bad_ttl(tmp_path):
    mod = _load_sync_module()
    good = tmp_path / "good.ttl"
    good.write_text(FIXTURE_TTL, encoding="utf-8")
    bad = tmp_path / "bad.ttl"
    bad.write_text("this is <not> valid turtle @@@", encoding="utf-8")
    # records use dest relative to repo root; here we pass absolute-ish via rel.
    rel_good = good.relative_to(tmp_path)
    # Build records pointing at tmp by temporarily chdir-ing repo root logic.
    records = [
        {"src": "g", "dest": str(good), "sha256": ""},
        {"src": "b", "dest": str(bad), "sha256": ""},
    ]
    # validate_vendored joins REPO_ROOT/dest; absolute dest still resolves.
    import os

    # Make dest absolute so REPO_ROOT / abs == abs
    records[0]["dest"] = str(good)
    records[1]["dest"] = str(bad)
    failures = mod.validate_vendored(records)
    assert any("bad.ttl" in f for f in failures)
    assert not any("good.ttl" in f for f in failures)
    _ = (rel_good, os)


# --------------------------------------------------------------------------
# Term-diff
# --------------------------------------------------------------------------
def test_compute_term_diff():
    mod = _load_sync_module()
    old = {"classes": ["A", "B"], "object_properties": ["p"], "datatype_properties": []}
    new = {"classes": ["B", "C"], "object_properties": ["p"], "datatype_properties": ["d"]}
    diff = mod.compute_term_diff(old, new)
    assert diff["added"] == ["C", "d"]
    assert diff["removed"] == ["A"]
    assert diff["added_count"] == 2
    assert diff["removed_count"] == 1
    assert diff["unchanged_count"] == 2  # B, p


def test_term_diff_empty_previous():
    mod = _load_sync_module()
    new = {"classes": ["X"], "object_properties": [], "datatype_properties": []}
    diff = mod.compute_term_diff({}, new)
    assert diff["added"] == ["X"]
    assert diff["removed"] == []


# --------------------------------------------------------------------------
# Lockfile schema
# --------------------------------------------------------------------------
def test_build_lock_schema():
    mod = _load_sync_module()
    lock = mod.build_lock(
        repo_url="https://example/repo",
        ref="main",
        commit_sha="abc123",
        records=[{"src": "a", "dest": "ontology/vendor/hcmo/a.ttl", "sha256": "0"}],
        upstream_ns="https://example.org/ns#",
        terms={"classes": ["A"], "object_properties": [], "datatype_properties": []},
    )
    for key in (
        "repo_url", "ref", "commit_sha", "synced_at", "files",
        "lab_namespace_detected", "upstream_namespace_detected", "ontology_terms",
    ):
        assert key in lock
    assert lock["files"][0]["sha256"] == "0"
    assert lock["upstream_namespace_detected"] == "https://example.org/ns#"


# --------------------------------------------------------------------------
# Config additions
# --------------------------------------------------------------------------
def test_config_exposes_sync_fields():
    config = pytest.importorskip("app.core.config")
    s = config.get_settings()
    assert s.HCMO_REPO_URL
    assert s.HCMO_REF
    assert str(s.HCMO_ACTIVE_SOURCE).lower() == "synthetic"
    assert s.vendor_ontology_dir.name == "hcmo"
    assert s.hcmo_lock_path.name == "HCMO_SYNC.lock.json"


def test_active_ontology_defaults_to_synthetic():
    config = pytest.importorskip("app.core.config")
    s = config.get_settings()
    # Default active source == synthetic => active path equals the synthetic
    # ontology_path, and is NOT under the vendor tree.
    assert s.active_ontology_path == s.ontology_path
    assert "vendor" not in str(s.active_ontology_path)


def test_active_ontology_vendor_flip():
    config = pytest.importorskip("app.core.config")
    s = config.Settings(HCMO_ACTIVE_SOURCE="vendor")
    assert "vendor" in str(s.active_ontology_path)
    assert s.active_ontology_path.name == "hcm.ttl"
