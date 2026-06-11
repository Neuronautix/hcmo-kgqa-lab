#!/usr/bin/env python3
"""Run SHACL validation over a chosen KG graph and report conformance.

By default validates ``kg/generated/merged_kg.ttl`` against the shapes in
``shacl/``. Prints conformance and any violations. With ``--strict`` the
process exits non-zero when the graph does not conform.

Usage:
    python scripts/validate_shacl.py [--graph merged|asserted|inferred|PATH] [--strict]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import die, get_settings, info, warn

_NAMED = {
    "merged": "merged_kg.ttl",
    "asserted": "asserted_kg.ttl",
    "inferred": "inferred_kg.ttl",
}


def _resolve_graph(value: str, out_dir: Path) -> Path:
    if value in _NAMED:
        return out_dir / _NAMED[value]
    return Path(value)


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="merged")
    parser.add_argument("--out-dir", default=str(settings.kg_generated_dir))
    parser.add_argument("--shapes-dir", default=str(settings.shacl_dir))
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero when the graph does not conform")
    args = parser.parse_args(argv)

    try:
        from app.shacl.validator import run_validation
    except Exception as exc:  # noqa: BLE001
        die(f"Could not import app.shacl.validator: {exc}")

    data_path = _resolve_graph(args.graph, Path(args.out_dir))
    if not data_path.exists():
        die(f"Data graph not found: {data_path}")

    info(f"Validating {data_path} against shapes in {args.shapes_dir}")
    report = run_validation(data_path, shapes_dir=args.shapes_dir)

    conforms = getattr(report, "conforms", True)
    violations = getattr(report, "violations", []) or []
    print(f"\nConforms: {conforms}")
    print(f"Violations: {len(violations)}")
    for v in violations:
        # ShaclViolation may be a model or dict; be tolerant.
        msg = getattr(v, "message", None) or (v.get("message") if isinstance(v, dict) else str(v))
        focus = getattr(v, "focus_node", None) or (v.get("focus_node") if isinstance(v, dict) else None)
        print(f"  - {focus or ''}: {msg}")

    if not conforms and args.strict:
        warn("Graph does not conform (strict mode).")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
