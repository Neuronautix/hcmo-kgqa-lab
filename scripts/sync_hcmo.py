#!/usr/bin/env python3
"""Pin, verify and drift-check the vendored HCMO release.

This is the lab's "sync layer". It is MANIFEST-DRIVEN and ONTOLOGY-AGNOSTIC:
nothing about the HCMO class names, properties or namespace is hardcoded here.
The upstream repo, the pinned release tag + commit SHA and the set of files to
vendor all live in ``sync/hcmo_sources.yaml``.

Modes (no secrets or tokens are ever required; upstream is public):

  (default) pin   Fetch the pinned release tag, refuse unless it resolves to
                  the manifest's ``commit_sha``, check each ``release_asset``
                  is byte-identical to the tagged file, vendor every file into
                  its ``dest``, validate RDF parses, write the lockfile with a
                  sha256 per file and print a term-diff vs the previous lock.
  --dry-run       Fetch + verify + term-diff only; writes nothing.
  --verify        OFFLINE: check the vendored files against the lockfile
                  sha256s and that the lockfile matches the manifest pin.
  --check-upstream
                  Report-only drift check: compare the pinned tag with the
                  latest upstream GitHub release (unauthenticated public API).
                  Writes a Markdown summary to $GITHUB_STEP_SUMMARY when set.
                  Never modifies files. Exit 0 unless --fail-on-drift.

Usage:
    python scripts/sync_hcmo.py [--manifest PATH] [--dry-run]
    python scripts/sync_hcmo.py --verify
    python scripts/sync_hcmo.py --check-upstream [--fail-on-drift]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- repo-root aware bootstrap --------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:  # defensive app.* import (shared helpers)
    from scripts._common import info, warn  # type: ignore
except Exception:  # noqa: BLE001 - keep runnable standalone
    def info(msg: str) -> None:
        print(f"[hcmo] {msg}")

    def warn(msg: str) -> None:
        print(f"[hcmo][warn] {msg}", file=sys.stderr)


DEFAULT_MANIFEST = REPO_ROOT / "sync" / "hcmo_sources.yaml"
DEFAULT_LOCKFILE = REPO_ROOT / "sync" / "HCMO_SYNC.lock.json"
ARCHIVE_DIR = REPO_ROOT / "ontology" / "vendor" / "_archive"

# Vendor root trees that get archived (and cleared) before re-vendoring.
VENDOR_TREES = [
    REPO_ROOT / "ontology" / "vendor" / "hcmo",
    REPO_ROOT / "shapes" / "vendor" / "hcmo",
    REPO_ROOT / "sparql" / "vendor" / "hcmo",
    REPO_ROOT / "kg" / "vendor" / "hcmo",
]

RDF_PARSE_SUFFIXES = {".ttl", ".owl", ".rdf", ".nt", ".n3"}
LAB_NAMESPACE = "http://w3id.org/hcmo#"  # the synthetic demo namespace


# ===========================================================================
# Manifest
# ===========================================================================
def load_manifest(path: Path) -> Dict[str, Any]:
    """Parse the YAML manifest and validate required keys.

    ``release_tag`` is the pinned ref; the legacy key ``ref`` is accepted as an
    alias so older manifests still load.
    """
    import yaml  # local import so the module stays import-safe

    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a YAML mapping")
    if "release_tag" not in data and "ref" in data:
        data["release_tag"] = data["ref"]
    for key in ("repo_url", "release_tag", "files"):
        if key not in data:
            raise ValueError(f"Manifest missing required key: {key!r}")
    if not isinstance(data["files"], list) or not data["files"]:
        raise ValueError("Manifest 'files' must be a non-empty list")
    for entry in data["files"]:
        if not isinstance(entry, dict) or "src" not in entry or "dest" not in entry:
            raise ValueError(f"Bad file entry (need src+dest): {entry!r}")
    return data


def primary_ontology_dest(manifest: Dict[str, Any]) -> Optional[str]:
    """Return the dest path of the primary ontology module.

    Honours an explicit ``primary_ontology`` pointer or a per-entry
    ``primary: true`` flag; otherwise falls back to the first ``ontology``
    kind. Returns a dest path (as written in the manifest) or None.
    """
    explicit = manifest.get("primary_ontology")
    if explicit:
        return str(explicit)
    for entry in manifest["files"]:
        if entry.get("primary"):
            return str(entry["dest"])
    for entry in manifest["files"]:
        if entry.get("kind") == "ontology":
            return str(entry["dest"])
    return None


def repo_slug(repo_url: str) -> str:
    """``https://github.com/owner/name(.git)`` -> ``owner/name``."""
    slug = repo_url.rstrip("/").removesuffix(".git")
    return slug.split("github.com/")[-1]


# ===========================================================================
# Fetch (public repo; no credentials)
# ===========================================================================
def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return out.stdout.strip()


def fetch_tag(repo_url: str, tag: str, dest: Path) -> str:
    """Shallow-clone ``tag`` into ``dest`` byte-exactly; return the commit SHA.

    ``core.autocrlf=false`` keeps line endings identical to the upstream blobs
    (and therefore to the release assets) on every platform.
    """
    info(f"Fetching {repo_url} @ {tag} (shallow git clone)...")
    _git(
        "-c", "core.autocrlf=false", "-c", "advice.detachedHead=false",
        "clone", "--quiet", "--depth", "1", "--branch", tag, repo_url, str(dest),
    )
    return _git("-C", str(dest), "rev-parse", "HEAD^{commit}")


def download_release_asset(repo_url: str, tag: str, name: str) -> bytes:
    """Download a public release asset (no token)."""
    import requests

    url = f"https://github.com/{repo_slug(repo_url)}/releases/download/{tag}/{name}"
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"release asset {url} -> HTTP {resp.status_code}")
    return resp.content


def latest_release_tag(repo_url: str) -> Optional[str]:
    """Return the tag of the upstream 'latest' release (unauthenticated)."""
    import requests

    url = f"https://api.github.com/repos/{repo_slug(repo_url)}/releases/latest"
    resp = requests.get(url, timeout=30, headers={"Accept": "application/vnd.github+json"})
    if resp.status_code != 200:
        raise RuntimeError(f"{url} -> HTTP {resp.status_code}")
    return resp.json().get("tag_name")


# ===========================================================================
# Hashing, vendor copy + archive
# ===========================================================================
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_and_clear(tag: str) -> None:
    """Best-effort copy of existing vendor trees into _archive/<tag>/
    (untracked), then clear them so files dropped upstream do not linger."""
    dest_root = ARCHIVE_DIR / tag
    for tree in VENDOR_TREES:
        if tree.exists() and any(p.is_file() and p.name != ".gitkeep" for p in tree.rglob("*")):
            rel = tree.relative_to(REPO_ROOT)
            try:
                shutil.copytree(tree, dest_root / rel, dirs_exist_ok=True)
                info(f"Archived previous {rel} -> {dest_root / rel}")
            except Exception as exc:  # noqa: BLE001 - best effort; files are in git
                warn(f"Archiving {rel} failed (continuing; previous files remain in git history): {exc}")
            for p in sorted(tree.rglob("*"), reverse=True):
                if p.is_file() and p.name != ".gitkeep":
                    p.unlink()
                elif p.is_dir() and not any(p.iterdir()):
                    p.rmdir()


def check_release_assets(manifest: Dict[str, Any], fetched: Path, repo_url: str, tag: str) -> List[str]:
    """Each ``release_asset`` must be byte-identical to its tagged ``src``."""
    problems: List[str] = []
    for entry in manifest["files"]:
        asset = entry.get("release_asset")
        if not asset:
            continue
        tree_file = fetched / entry["src"]
        try:
            blob = download_release_asset(repo_url, tag, asset)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{asset}: {exc}")
            continue
        if not tree_file.exists():
            problems.append(f"{asset}: tagged file {entry['src']} missing")
        elif hashlib.sha256(blob).hexdigest() != _sha256(tree_file):
            problems.append(f"{asset}: release asset differs from {entry['src']} at {tag}")
        else:
            info(f"Release asset {asset} == {entry['src']} @ {tag}")
    return problems


def copy_files(manifest: Dict[str, Any], fetched: Path) -> List[Dict[str, str]]:
    """Copy each manifest file from the fetched repo into its dest.

    Returns a list of {src, dest, sha256[, release_asset]} records. A missing
    upstream file is an error (the pin must be complete).
    """
    records: List[Dict[str, str]] = []
    for entry in manifest["files"]:
        src = fetched / entry["src"]
        dest = REPO_ROOT / entry["dest"]
        if not src.exists():
            raise FileNotFoundError(f"Upstream file missing at pinned tag: {entry['src']}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        rec = {"src": entry["src"], "dest": entry["dest"], "sha256": _sha256(dest)}
        if entry.get("release_asset"):
            rec["release_asset"] = entry["release_asset"]
        records.append(rec)
    return records


# ===========================================================================
# Validation, namespace + term detection
# ===========================================================================
def validate_vendored(records: List[Dict[str, str]]) -> List[str]:
    """Parse every vendored RDF file with rdflib; return list of failures."""
    from rdflib import Graph

    failures: List[str] = []
    for rec in records:
        dest = REPO_ROOT / rec["dest"]
        if dest.suffix.lower() not in RDF_PARSE_SUFFIXES:
            continue
        try:
            Graph().parse(str(dest), format="turtle")
        except Exception:  # noqa: BLE001
            try:
                Graph().parse(str(dest))  # let rdflib guess
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{rec['dest']}: {exc}")
    return failures


def _local_name(iri: str) -> str:
    for sep in ("#", "/"):
        if sep in iri:
            return iri.rsplit(sep, 1)[-1]
    return iri


def _parse(path: Path):
    from rdflib import Graph

    g = Graph()
    try:
        g.parse(str(path), format="turtle")
    except Exception:  # noqa: BLE001
        g.parse(str(path))
    return g


def detect_namespace(ontology_path: Path) -> Optional[str]:
    """Detect the upstream ontology namespace by parsing the file.

    Prefers the owl:Ontology subject IRI; falls back to the most common
    namespace among declared owl terms. Never hardcodes a namespace.
    """
    from rdflib import OWL, RDF, URIRef

    if not ontology_path.exists():
        return None
    try:
        g = _parse(ontology_path)
    except Exception:  # noqa: BLE001
        return None
    # A merged release graph can declare several owl:Ontology nodes (e.g. an
    # imported upper-level presentation module). Prefer the one carrying an
    # owl:versionIRI (the release itself), then the lexically first.
    ontologies = sorted(
        (s for s in g.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)),
        key=lambda s: (g.value(s, OWL.versionIRI) is None, str(s)),
    )
    if ontologies:
        iri = str(ontologies[0])
        # Ontology IRI often lacks the '#'; append it if a hash ns is implied.
        return iri if iri.endswith(("#", "/")) else iri + "#"
    from collections import Counter

    counter: Counter = Counter()
    for t in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty):
        for s in g.subjects(RDF.type, t):
            iri = str(s)
            for sep in ("#", "/"):
                if sep in iri:
                    counter[iri.rsplit(sep, 1)[0] + sep] += 1
                    break
    return counter.most_common(1)[0][0] if counter else None


def collect_terms(ontology_path: Path) -> Dict[str, List[str]]:
    """Return sorted local-name lists of owl classes/object/datatype props."""
    from rdflib import OWL, RDF, URIRef

    result: Dict[str, List[str]] = {
        "classes": [], "object_properties": [], "datatype_properties": [],
    }
    if not ontology_path.exists():
        return result
    try:
        g = _parse(ontology_path)
    except Exception:  # noqa: BLE001
        return result
    mapping = [
        (OWL.Class, "classes"),
        (OWL.ObjectProperty, "object_properties"),
        (OWL.DatatypeProperty, "datatype_properties"),
    ]
    for rdf_type, key in mapping:
        names = {
            _local_name(str(s))
            for s in g.subjects(RDF.type, rdf_type)
            if isinstance(s, URIRef)
        }
        result[key] = sorted(names)
    return result


# ===========================================================================
# Term diff
# ===========================================================================
def compute_term_diff(old: Dict[str, List[str]], new: Dict[str, List[str]]) -> Dict[str, Any]:
    """Compare two term sets (flattened across categories)."""
    def flatten(d: Dict[str, List[str]]) -> set:
        return set().union(*(set(d.get(k, [])) for k in
                             ("classes", "object_properties", "datatype_properties"))) \
            if d else set()

    old_set, new_set = flatten(old), flatten(new)
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    unchanged = sorted(new_set & old_set)
    return {
        "added": added,
        "removed": removed,
        "unchanged_count": len(unchanged),
        "added_count": len(added),
        "removed_count": len(removed),
    }


# ===========================================================================
# Lockfile
# ===========================================================================
def read_lock(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def build_lock(
    repo_url: str,
    ref: str,
    commit_sha: str,
    records: List[Dict[str, str]],
    upstream_ns: Optional[str],
    terms: Dict[str, List[str]],
    version: Optional[str] = None,
    version_iri: Optional[str] = None,
    concept_doi: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "repo_url": repo_url,
        "ref": ref,
        "release_tag": ref,
        "commit_sha": commit_sha,
        "version": version,
        "version_iri": version_iri,
        "concept_doi": concept_doi,
        "synced_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "files": records,
        "lab_namespace_detected": LAB_NAMESPACE,
        "upstream_namespace_detected": upstream_ns,
        "ontology_terms": terms,
    }


def verify_lock(manifest: Dict[str, Any], lock: Dict[str, Any]) -> List[str]:
    """Offline check: lock matches the manifest pin and every vendored file
    matches its recorded sha256. Returns a list of problems (empty == OK)."""
    problems: List[str] = []
    if not lock:
        return ["lockfile missing or unreadable"]
    for key in ("repo_url", "release_tag", "commit_sha"):
        if key in manifest and lock.get(key) != manifest[key]:
            problems.append(f"lock {key}={lock.get(key)!r} != manifest {manifest[key]!r}")
    locked = {r["dest"]: r for r in lock.get("files", [])}
    wanted = {str(e["dest"]) for e in manifest["files"]}
    for dest in sorted(wanted - set(locked)):
        problems.append(f"{dest}: in manifest but not in lockfile")
    for dest in sorted(set(locked) - wanted):
        problems.append(f"{dest}: in lockfile but not in manifest")
    for dest, rec in sorted(locked.items()):
        path = REPO_ROOT / dest
        if not path.exists():
            problems.append(f"{dest}: missing")
        elif _sha256(path) != rec.get("sha256"):
            problems.append(f"{dest}: sha256 mismatch (local edit or line-ending conversion?)")
    return problems


# ===========================================================================
# Modes
# ===========================================================================
def _summary(lines: List[str]) -> None:
    text = "\n".join(lines) + "\n"
    print(text)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text)


def run_verify(manifest: Dict[str, Any]) -> int:
    problems = verify_lock(manifest, read_lock(DEFAULT_LOCKFILE))
    lines = [
        "## Vendored HCMO integrity",
        "",
        f"Pinned: `{manifest['repo_url']}` @ `{manifest['release_tag']}` "
        f"(`{manifest.get('commit_sha', '?')}`)",
        "",
    ]
    if problems:
        lines += ["**FAIL**", ""] + [f"- {p}" for p in problems]
    else:
        lines.append(f"OK: {len(manifest['files'])} vendored files match the lockfile sha256s.")
    _summary(lines)
    return 1 if problems else 0


def run_check_upstream(manifest: Dict[str, Any], fail_on_drift: bool) -> int:
    pinned = manifest["release_tag"]
    try:
        latest = latest_release_tag(manifest["repo_url"])
    except Exception as exc:  # noqa: BLE001
        _summary(["## HCMO upstream drift", "", f"Could not query upstream: {exc}"])
        return 0
    lines = ["## HCMO upstream drift", "", f"- pinned: `{pinned}`", f"- latest upstream release: `{latest}`", ""]
    drift = latest is not None and latest != pinned
    if drift:
        lines.append(
            "A newer HCMO release exists. To adopt it, follow the manual pinning "
            "steps in `docs/hcmo_sync.md` (edit `sync/hcmo_sources.yaml`, run "
            "`python scripts/sync_hcmo.py`, review the term-diff and the "
            "competency-question answers, record a migration note)."
        )
    else:
        lines.append("The lab is pinned to the latest upstream release.")
    _summary(lines)
    return 1 if (drift and fail_on_drift) else 0


def run_pin(manifest: Dict[str, Any], dry_run: bool) -> int:
    repo_url = manifest["repo_url"]
    tag = manifest["release_tag"]
    expected_sha = manifest.get("commit_sha")
    info(f"Repo: {repo_url}  tag: {tag}  commit: {expected_sha}  dry-run: {dry_run}")

    prev_lock = read_lock(DEFAULT_LOCKFILE)
    prev_terms = prev_lock.get("ontology_terms", {})

    with tempfile.TemporaryDirectory(prefix="hcmo_sync_") as tmp:
        fetched = Path(tmp) / "hcmo"
        try:
            commit_sha = fetch_tag(repo_url, tag, fetched)
        except Exception as exc:  # noqa: BLE001
            warn(f"Could not fetch {repo_url} @ {tag}: {exc}")
            return 3
        info(f"Resolved commit SHA: {commit_sha}")
        if expected_sha and commit_sha != expected_sha:
            warn(f"Tag {tag} resolves to {commit_sha}, manifest pins {expected_sha}. Refusing.")
            return 4

        asset_problems = check_release_assets(manifest, fetched, repo_url, tag)
        if asset_problems:
            for p in asset_problems:
                warn(p)
            return 5

        prim_dest = primary_ontology_dest(manifest)
        prim_src = next(
            (fetched / e["src"] for e in manifest["files"] if str(e["dest"]) == prim_dest),
            None,
        )
        upstream_ns = detect_namespace(prim_src) if prim_src else None
        new_terms = collect_terms(prim_src) if prim_src else {}
        info(f"Detected upstream namespace: {upstream_ns}")

        diff = compute_term_diff(prev_terms, new_terms)
        info("=" * 60)
        info("TERM-DIFF REPORT (vs previous lockfile)")
        info(f"  unchanged: {diff['unchanged_count']}")
        info(f"  added:     {diff['added_count']}  {diff['added'] or ''}")
        info(f"  removed:   {diff['removed_count']}  {diff['removed'] or ''}")
        info("=" * 60)

        if dry_run:
            info("Dry run: no vendor files written, no lockfile updated.")
            return 0

        archive_previous_tag = str(prev_lock.get("commit_sha") or "unversioned")
        archive_and_clear(archive_previous_tag)
        records = copy_files(manifest, fetched)
        info(f"Vendored {len(records)} files.")

    failures = validate_vendored(records)
    if failures:
        warn("RDF parse failures in vendored files:")
        for f in failures:
            warn(f"  {f}")

    lock = build_lock(
        repo_url, tag, commit_sha, records, upstream_ns, new_terms,
        version=manifest.get("version"),
        version_iri=manifest.get("version_iri"),
        concept_doi=manifest.get("concept_doi"),
    )
    DEFAULT_LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOCKFILE.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    info(f"Wrote lockfile -> {DEFAULT_LOCKFILE}")

    info("=" * 60)
    info("PIN SUMMARY")
    info(f"  repo:       {repo_url}")
    info(f"  tag:        {tag}")
    info(f"  commit:     {commit_sha}")
    info(f"  files:      {len(records)} vendored")
    info(f"  namespace:  {upstream_ns}")
    info(f"  classes:    {len(new_terms.get('classes', []))}")
    info(f"  obj props:  {len(new_terms.get('object_properties', []))}")
    info(f"  data props: {len(new_terms.get('datatype_properties', []))}")
    info(f"  term-diff:  +{diff['added_count']} / -{diff['removed_count']}")
    info("=" * 60)
    return 1 if failures else 0


# ===========================================================================
# main
# ===========================================================================
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="Fetch + verify + term-diff; write nothing")
    mode.add_argument("--verify", action="store_true",
                      help="Offline: check vendored files against the lockfile")
    mode.add_argument("--check-upstream", action="store_true",
                      help="Report whether a newer upstream release exists")
    parser.add_argument("--fail-on-drift", action="store_true",
                        help="With --check-upstream: exit 1 when a newer release exists")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(Path(args.manifest))
    except Exception as exc:  # noqa: BLE001
        warn(f"Could not load manifest: {exc}")
        return 2

    if args.verify:
        return run_verify(manifest)
    if args.check_upstream:
        return run_check_upstream(manifest, args.fail_on_drift)
    return run_pin(manifest, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
