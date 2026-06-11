#!/usr/bin/env python3
"""Reset the demo to a clean, reproducible state.

Steps:
  1. Delete generated artifacts in ``kg/generated/`` (keeps .gitkeep).
  2. Clear the Fuseki dataset (best-effort; skipped if Fuseki is unreachable).
  3. Re-run merge -> reason -> (optionally) load.

The pipeline steps are invoked by importing the sibling scripts' ``main``
functions so a single Python process drives the whole reset.

Usage:
    python scripts/reset_demo.py [--no-load] [--keep-generated]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import get_settings, info, warn


def _clear_generated(out_dir: Path) -> None:
    for ttl in out_dir.glob("*.ttl"):
        try:
            ttl.unlink()
            info(f"Removed {ttl.name}")
        except OSError as exc:
            warn(f"Could not remove {ttl}: {exc}")
    gitkeep = out_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()


def _clear_fuseki(settings) -> None:
    try:
        from app.kg import jena_admin
    except Exception as exc:  # noqa: BLE001
        warn(f"jena_admin unavailable: {exc}")
        return
    clear = getattr(jena_admin, "clear_dataset", None)
    if clear is None:
        warn("jena_admin.clear_dataset not available; skipping Fuseki clear")
        return
    try:
        ok = clear(settings)
        info(f"Cleared Fuseki dataset: {ok}")
    except Exception as exc:  # noqa: BLE001
        warn(f"Could not clear Fuseki (is it running?): {exc}")


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-load", action="store_true",
                        help="Skip loading into Fuseki (offline rebuild only)")
    parser.add_argument("--keep-generated", action="store_true",
                        help="Do not delete existing generated TTL first")
    args = parser.parse_args(argv)

    out_dir = Path(settings.kg_generated_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.keep_generated:
        info("Clearing generated artifacts...")
        _clear_generated(out_dir)

    _clear_fuseki(settings)

    import merge_rdf_graphs
    import materialize_reasoning

    info("Running merge...")
    if merge_rdf_graphs.main([]) != 0:
        warn("merge step failed")
        return 1
    info("Running reasoning...")
    if materialize_reasoning.main([]) != 0:
        warn("reasoning step failed")
        return 1

    if not args.no_load:
        import load_to_fuseki

        info("Loading into Fuseki...")
        try:
            load_to_fuseki.main(["--named"])
        except SystemExit as exc:
            if exc.code:
                warn("load step failed (Fuseki may be down); demo files are "
                    "still rebuilt locally.")

    info("Reset complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
