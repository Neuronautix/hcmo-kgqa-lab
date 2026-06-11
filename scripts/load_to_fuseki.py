#!/usr/bin/env python3
"""Load generated KG files into Apache Jena/Fuseki via the Graph Store Protocol.

Creates the dataset if it does not yet exist (using ``app.kg.jena_admin``) and
uploads ``merged_kg.ttl`` to the default graph. Optionally uploads the
asserted/inferred graphs into named graphs.

Named-graph IRIs:
    asserted  -> http://w3id.org/hcmo/graph/asserted
    inferred  -> http://w3id.org/hcmo/graph/inferred

Usage:
    python scripts/load_to_fuseki.py [--file PATH] [--named] [--clear]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import die, get_settings, info, warn

ASSERTED_GRAPH = "http://w3id.org/hcmo/graph/asserted"
INFERRED_GRAPH = "http://w3id.org/hcmo/graph/inferred"


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=None, help="Turtle file for the default graph")
    parser.add_argument("--out-dir", default=str(settings.kg_generated_dir))
    parser.add_argument("--named", action="store_true",
                        help="Also upload asserted/inferred into named graphs")
    parser.add_argument("--clear", action="store_true",
                        help="Clear the dataset before loading")
    args = parser.parse_args(argv)

    try:
        from app.kg import graph_loader, jena_admin
    except Exception as exc:  # noqa: BLE001
        die(f"Could not import app.kg loader/admin: {exc}")

    out_dir = Path(args.out_dir)
    merged = Path(args.file) if args.file else out_dir / "merged_kg.ttl"
    if not merged.exists():
        die(f"{merged} not found; run merge/reason first")

    # 1. Ensure dataset exists.
    create = getattr(jena_admin, "create_dataset", None)
    if create:
        ok = create(settings)
        info(f"Dataset '{settings.FUSEKI_DATASET}' ready: {ok}")
    else:
        warn("jena_admin.create_dataset not available; assuming dataset exists")

    # 2. Optionally clear.
    if args.clear:
        clear = getattr(jena_admin, "clear_dataset", None)
        if clear:
            clear(settings)
            info("Cleared dataset")

    # 3. Upload default graph.
    upload = getattr(graph_loader, "upload_turtle", None)
    if upload is None:
        die("graph_loader.upload_turtle not available")
    upload(merged, None, settings)
    info(f"Uploaded {merged.name} to default graph at {settings.gsp_endpoint}")

    # 4. Optional named graphs.
    if args.named:
        for fname, guri in (("asserted_kg.ttl", ASSERTED_GRAPH),
                            ("inferred_kg.ttl", INFERRED_GRAPH)):
            fpath = out_dir / fname
            if fpath.exists():
                upload(fpath, guri, settings)
                info(f"Uploaded {fname} -> <{guri}>")
            else:
                warn(f"{fpath} missing; skipping named graph <{guri}>")

    info("Load complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
