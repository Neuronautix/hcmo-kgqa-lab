#!/usr/bin/env python3
"""Evaluate the vendored HCMO release offline (no network, no LLM).

Runs every upstream competency question against the vendored release graph
plus the vendored positive examples and compares the rows with the reviewed
``expected_answers``; then runs the vendored SHACL shapes against each vendored
example. Exit code 1 if anything fails.

Usage:
    python scripts/eval_hcmo_release.py [--no-shacl] [--report PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.evaluation.hcmo_release import (  # noqa: E402
    VendoredRelease,
    run_competency_questions,
    run_shacl,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-shacl", action="store_true")
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)

    rel = VendoredRelease.load()
    print(f"HCMO {rel.pin.get('version')} ({rel.pin.get('release_tag')} @ {rel.pin.get('commit_sha')})")
    cqs = run_competency_questions(rel)
    print(f"\nCompetency questions ({len(cqs)}):")
    for r in cqs:
        mark = "PASS" if r.ok else "FAIL"
        print(f"  [{mark}] {r.id:38} rows={len(r.actual)} expected={len(r.expected)}")
        if r.error:
            print(f"         error: {r.error}")
    shacl = [] if args.no_shacl else run_shacl(rel)
    if shacl:
        print(f"\nSHACL ({len(shacl)} examples):")
        for s in shacl:
            want = "non-conformant" if s.negative else "conformant"
            got = "conformant" if s.conforms else "non-conformant"
            print(f"  [{'PASS' if s.ok else 'FAIL'}] {s.example:40} expected {want}, got {got}")

    n_ok = sum(r.ok for r in cqs) + sum(s.ok for s in shacl)
    n = len(cqs) + len(shacl)
    print(f"\nSummary: {n_ok}/{n} checks passed")
    if args.report:
        Path(args.report).write_text(json.dumps({
            "competency_questions": [
                {"id": r.id, "ok": r.ok, "expected": r.expected, "actual": r.actual, "error": r.error}
                for r in cqs
            ],
            "shacl": [{"example": s.example, "negative": s.negative, "conforms": s.conforms} for s in shacl],
        }, indent=2), encoding="utf-8")
    return 0 if n_ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
