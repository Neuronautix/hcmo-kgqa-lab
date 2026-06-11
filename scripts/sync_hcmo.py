#!/usr/bin/env python3
"""Sync the canonical HCMO ontology, SHACL shapes and competency queries from
the upstream HCMO repository into this lab's ``*/vendor/`` trees.

This is the "sync layer". It is MANIFEST-DRIVEN and ONTOLOGY-AGNOSTIC: nothing
about the HCMO class names, properties or namespace is hardcoded here. The set
of files to fetch, the upstream repo and the tracked git ref all live in
``sync/hcmo_sources.yaml``. When upstream is reshaped you only edit the
manifest -- this script keeps working.

What it does:
  * read the manifest,
  * shallow ``git clone`` the upstream repo at the requested ref (falls back to
    raw.githubusercontent.com per-file download if git is unavailable),
  * resolve the actual commit SHA,
  * archive the previous vendor tree, then copy each manifest file into place,
  * validate every vendored .ttl/.owl parses with rdflib,
  * detect the upstream namespace and ontology term set by PARSING the files,
  * write a reproducible lockfile (sync/HCMO_SYNC.lock.json),
  * print a TERM-DIFF report vs the previous lockfile,
  * build a profile of the vendored ontology (ontology/vendor/hcmo/profile.json).

It never touches the synthetic demo model (ontology/current, ontology/profiles,
shacl/, sparql/, kg/examples).

Usage:
    python scripts/sync_hcmo.py [--ref REF] [--repo-url URL]
                                [--manifest PATH] [--no-profile] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

# Vendor root trees that get archived before an overwrite.
VENDOR_TREES = [
    REPO_ROOT / "ontology" / "vendor" / "hcmo",
    REPO_ROOT / "shapes" / "vendor",
    REPO_ROOT / "sparql" / "vendor",
    REPO_ROOT / "kg" / "vendor",
]

RDF_PARSE_SUFFIXES = {".ttl", ".owl", ".rdf", ".nt", ".n3"}


# ===========================================================================
# Manifest
# ===========================================================================
def load_manifest(path: Path) -> Dict[str, Any]:
    """Parse the YAML manifest and validate required keys."""
    import yaml  # local import so the module stays import-safe

    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a YAML mapping")
    for key in ("repo_url", "ref", "files"):
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


# ===========================================================================
# Fetch
# ===========================================================================
def _git_clone(repo_url: str, ref: str, dest: Path) -> Optional[str]:
    """Shallow clone and return the resolved commit SHA, or None on failure."""
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", ref, repo_url, str(dest)],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:  # noqa: BLE001
        # --branch fails for raw commit SHAs; try a full-ish clone + checkout.
        try:
            subprocess.run(
                ["git", "clone", repo_url, str(dest)],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "-C", str(dest), "checkout", ref],
                check=True, capture_output=True, text=True,
            )
        except Exception:  # noqa: BLE001
            warn(f"git clone failed: {exc}")
            return None
    try:
        out = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def _raw_download(repo_url: str, ref: str, manifest: Dict[str, Any], dest: Path) -> Optional[str]:
    """Fallback: download each manifest src from raw.githubusercontent.com."""
    try:
        import requests
    except Exception:  # noqa: BLE001
        warn("requests not available; cannot use raw fallback")
        return None
    slug = repo_url.rstrip("/").removesuffix(".git")
    slug = slug.split("github.com/")[-1]
    base = f"https://raw.githubusercontent.com/{slug}/{ref}"
    ok = False
    for entry in manifest["files"]:
        url = f"{base}/{entry['src']}"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                warn(f"raw fetch {url} -> HTTP {resp.status_code}")
                continue
            target = dest / entry["src"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(resp.content)
            ok = True
        except Exception as exc:  # noqa: BLE001
            warn(f"raw fetch failed for {url}: {exc}")
    return ref if ok else None  # SHA unknown via raw -> record the ref


def fetch_repo(repo_url: str, ref: str, manifest: Dict[str, Any], dest: Path) -> str:
    """Fetch upstream into ``dest`` and return the resolved commit SHA/ref."""
    info(f"Fetching {repo_url} @ {ref} (shallow git clone)...")
    sha = _git_clone(repo_url, ref, dest)
    if sha:
        info(f"Resolved commit SHA: {sha}")
        return sha
    warn("git clone unavailable -- falling back to raw.githubusercontent.com")
    sha = _raw_download(repo_url, ref, manifest, dest)
    if not sha:
        raise RuntimeError(
            f"Could not fetch {repo_url} @ {ref} via git or raw download. "
            "Check network access / the ref name."
        )
    info(f"Fetched via raw download (commit SHA unknown; recording ref={sha})")
    return sha


# ===========================================================================
# Vendor copy + archive
# ===========================================================================
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_previous(tag: str) -> None:
    """Best-effort copy of existing vendor trees into _archive/<tag>/."""
    try:
        any_existing = any(t.exists() and any(t.rglob("*")) for t in VENDOR_TREES)
        if not any_existing:
            return
        dest_root = ARCHIVE_DIR / tag
        for tree in VENDOR_TREES:
            if tree.exists() and any(tree.rglob("*")):
                rel = tree.relative_to(REPO_ROOT)
                shutil.copytree(tree, dest_root / rel, dirs_exist_ok=True)
        info(f"Archived previous vendor tree -> {dest_root}")
    except Exception as exc:  # noqa: BLE001
        warn(f"Archiving previous vendor tree failed (continuing): {exc}")


def copy_files(manifest: Dict[str, Any], fetched: Path) -> List[Dict[str, str]]:
    """Copy each manifest file from the fetched repo into its dest.

    Returns a list of {src, dest, sha256} records (dest relative to repo root).
    """
    records: List[Dict[str, str]] = []
    for entry in manifest["files"]:
        src = fetched / entry["src"]
        dest = REPO_ROOT / entry["dest"]
        if not src.exists():
            warn(f"Upstream file missing, skipping: {entry['src']}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        records.append(
            {"src": entry["src"], "dest": entry["dest"], "sha256": _sha256(dest)}
        )
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


def detect_namespace(ontology_path: Path) -> Optional[str]:
    """Detect the upstream ontology namespace by parsing the file.

    Prefers the owl:Ontology subject IRI; falls back to the most common
    namespace among declared owl terms. Never hardcodes a namespace.
    """
    from rdflib import OWL, RDF, Graph

    if not ontology_path.exists():
        return None
    g = Graph()
    try:
        g.parse(str(ontology_path), format="turtle")
    except Exception:  # noqa: BLE001
        try:
            g.parse(str(ontology_path))
        except Exception:  # noqa: BLE001
            return None
    for s in g.subjects(RDF.type, OWL.Ontology):
        iri = str(s)
        # Ontology IRI often lacks the '#'; append it if a hash ns is implied.
        return iri if iri.endswith(("#", "/")) else iri + "#"
    # Fallback: most common namespace among declared classes/properties.
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
    from rdflib import OWL, RDF, Graph, URIRef

    result = {"classes": [], "object_properties": [], "datatype_properties": []}
    if not ontology_path.exists():
        return result
    g = Graph()
    try:
        g.parse(str(ontology_path), format="turtle")
    except Exception:  # noqa: BLE001
        try:
            g.parse(str(ontology_path))
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
# Profile
# ===========================================================================
def build_vendor_profile(ontology_paths: List[Path], out_path: Path) -> None:
    """Build a profile of the merged vendored ontology and write it out.

    Reuses app.ontology.profiler.build_profile if importable; otherwise uses a
    small inline rdflib profiler. Never overwrites the synthetic profiles.
    """
    from rdflib import Graph

    g = Graph()
    for p in ontology_paths:
        if p.exists() and p.suffix.lower() in RDF_PARSE_SUFFIXES:
            try:
                g.parse(str(p), format="turtle")
            except Exception:  # noqa: BLE001
                try:
                    g.parse(str(p))
                except Exception:  # noqa: BLE001
                    pass
    profile: Dict[str, Any]
    try:
        from app.ontology.profiler import build_profile  # type: ignore

        profile = build_profile(g)
    except Exception:  # noqa: BLE001 - inline fallback
        from rdflib import OWL, RDF, URIRef

        def collect(t):
            return sorted(
                {str(s) for s in g.subjects(RDF.type, t) if isinstance(s, URIRef)}
            )

        classes = collect(OWL.Class)
        obj = collect(OWL.ObjectProperty)
        dat = collect(OWL.DatatypeProperty)
        profile = {
            "classes": [{"iri": c, "local_name": _local_name(c)} for c in classes],
            "object_properties": [{"iri": c, "local_name": _local_name(c)} for c in obj],
            "datatype_properties": [{"iri": c, "local_name": _local_name(c)} for c in dat],
            "counts": {
                "classes": len(classes),
                "object_properties": len(obj),
                "datatype_properties": len(dat),
                "triples": len(g),
            },
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    info(f"Wrote vendored profile -> {out_path}")


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
) -> Dict[str, Any]:
    return {
        "repo_url": repo_url,
        "ref": ref,
        "commit_sha": commit_sha,
        "synced_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "files": records,
        "lab_namespace_detected": "http://w3id.org/hcmo#",  # the synthetic demo ns
        "upstream_namespace_detected": upstream_ns,
        "ontology_terms": terms,
    }


# ===========================================================================
# main
# ===========================================================================
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default=None, help="Override the manifest git ref")
    parser.add_argument("--repo-url", default=None, help="Override the manifest repo URL")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--no-profile", action="store_true", help="Skip building the vendor profile")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch + report term-diff but do not write vendor files/lockfile")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(Path(args.manifest))
    except Exception as exc:  # noqa: BLE001
        warn(f"Could not load manifest: {exc}")
        return 2

    repo_url = args.repo_url or manifest["repo_url"]
    ref = args.ref or manifest["ref"]
    info(f"Manifest: {args.manifest}")
    info(f"Repo: {repo_url}  ref: {ref}  dry-run: {args.dry_run}")

    prev_lock = read_lock(DEFAULT_LOCKFILE)
    prev_terms = prev_lock.get("ontology_terms", {})

    with tempfile.TemporaryDirectory(prefix="hcmo_sync_") as tmp:
        fetched = Path(tmp)
        try:
            commit_sha = fetch_repo(repo_url, ref, manifest, fetched)
        except Exception as exc:  # noqa: BLE001
            warn(str(exc))
            return 3

        prim_dest = primary_ontology_dest(manifest)
        # Locate the primary ontology *inside the fetched repo* for detection.
        prim_src = None
        for entry in manifest["files"]:
            if str(entry["dest"]) == prim_dest:
                prim_src = fetched / entry["src"]
                break

        upstream_ns = detect_namespace(prim_src) if prim_src else None
        new_terms = collect_terms(prim_src) if prim_src else {}
        info(f"Detected upstream namespace: {upstream_ns}")

        # --- Term diff (works in dry-run too) ---------------------------
        diff = compute_term_diff(prev_terms, new_terms)
        info("=" * 60)
        info("TERM-DIFF REPORT (vs previous lockfile)")
        info(f"  unchanged: {diff['unchanged_count']}")
        info(f"  added:     {diff['added_count']}  {diff['added'] or ''}")
        info(f"  removed:   {diff['removed_count']}  {diff['removed'] or ''}")
        info("=" * 60)

        if args.dry_run:
            info("Dry run: no vendor files written, no lockfile updated.")
            # Validate the fetched primary still parses, for signal.
            if prim_src and prim_src.suffix.lower() in RDF_PARSE_SUFFIXES:
                fails = []
                try:
                    from rdflib import Graph
                    Graph().parse(str(prim_src), format="turtle")
                except Exception as exc:  # noqa: BLE001
                    fails.append(str(exc))
                if fails:
                    warn(f"Primary ontology parse issues: {fails}")
            info("Dry run complete.")
            return 0

        # --- Archive + copy --------------------------------------------
        archive_tag = (prev_lock.get("commit_sha")
                       or _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        archive_previous(str(archive_tag))
        records = copy_files(manifest, fetched)
        info(f"Vendored {len(records)} files.")

    # --- Validate vendored RDF (outside tempdir; files are in place) ---
    failures = validate_vendored(records)
    if failures:
        warn("RDF parse failures in vendored files:")
        for f in failures:
            warn(f"  {f}")

    # --- Profile ------------------------------------------------------
    if not args.no_profile:
        ont_paths = [
            REPO_ROOT / e["dest"]
            for e in manifest["files"]
            if e.get("kind") == "ontology"
        ]
        build_vendor_profile(
            ont_paths, REPO_ROOT / "ontology" / "vendor" / "hcmo" / "profile.json"
        )

    # --- Lockfile -----------------------------------------------------
    lock = build_lock(repo_url, ref, commit_sha, records, upstream_ns, new_terms)
    DEFAULT_LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOCKFILE.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    info(f"Wrote lockfile -> {DEFAULT_LOCKFILE}")

    # --- Summary ------------------------------------------------------
    info("=" * 60)
    info("SYNC SUMMARY")
    info(f"  repo:       {repo_url}")
    info(f"  ref:        {ref}")
    info(f"  commit:     {commit_sha}")
    info(f"  files:      {len(records)} vendored")
    info(f"  namespace:  {upstream_ns}")
    info(f"  classes:    {len(new_terms.get('classes', []))}")
    info(f"  obj props:  {len(new_terms.get('object_properties', []))}")
    info(f"  data props: {len(new_terms.get('datatype_properties', []))}")
    info(f"  term-diff:  +{diff['added_count']} / -{diff['removed_count']}")
    info("=" * 60)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
