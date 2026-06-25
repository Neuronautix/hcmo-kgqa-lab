#!/usr/bin/env python3
"""Offline demo backend: a Fuseki-compatible SPARQL endpoint backed by rdflib.

For demos and local development where the real Apache Jena/Fuseki container is
not available (no Docker, restricted network, CI). It speaks just enough of the
Fuseki HTTP API for the HCMO-KGQA app, the SPARQL Playground and the evaluation
harness to work against ``http://localhost:3030`` unchanged:

    GET  /$/datasets[/<name>]   -> dataset exists / list (no-op admin)
    POST /$/datasets            -> create dataset (no-op)
    GET|POST  /<ds>/sparql      -> SPARQL SELECT/ASK/CONSTRUCT (JSON / turtle)
    GET|POST  /<ds>/query       -> alias of /sparql
    POST /<ds>/update           -> SPARQL UPDATE (incl. CLEAR ALL)
    GET|POST|PUT /<ds>/data     -> Graph Store Protocol load/replace

The dataset is seeded from ``kg/generated/merged_kg.ttl`` (run ``make merge``
or ``make demo`` first); GSP uploads merge/replace into the in-memory graph.

Usage:
    python scripts/demo_serve.py [--port 3030] [--ttl PATH]

This is a development convenience, NOT a production triple store: it keeps the
graph in memory and implements only the endpoints the app touches.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from _common import get_settings, info, warn

from rdflib import Graph


def _build_handler(graph: Graph):
    def _form(body: bytes) -> dict:
        return {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console quiet
            pass

        def _send(self, code, body=b"", ctype="text/plain"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read(self) -> bytes:
            n = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(n) if n else b""

        # -------------------------------------------------------------- #
        def do_GET(self):
            path = urlparse(self.path).path
            qs = parse_qs(urlparse(self.path).query)
            if path.startswith("/$/datasets"):
                return self._send(200, '{"datasets":[{"ds.name":"/hcmo"}]}', "application/json")
            if path.endswith("/sparql") or path.endswith("/query"):
                q = qs.get("query", [None])[0]
                return self._run_query(q) if q else self._send(200, "ok")
            if path.endswith("/data"):
                return self._send(200, graph.serialize(format="turtle"), "text/turtle")
            return self._send(200, "ok")

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._read()
            if path.startswith("/$/datasets"):
                return self._send(200, "created")
            if path.endswith("/update"):
                try:
                    graph.update(_form(body).get("update", ""))
                except Exception as exc:  # noqa: BLE001
                    return self._send(400, f"update failed: {exc}")
                return self._send(200, "updated")
            if path.endswith("/sparql") or path.endswith("/query"):
                ctype = self.headers.get("Content-Type", "")
                q = body.decode() if "sparql-query" in ctype else _form(body).get("query", "")
                return self._run_query(q)
            if path.endswith("/data"):
                return self._load_gsp(body)
            return self._send(200, "ok")

        def do_PUT(self):
            if urlparse(self.path).path.endswith("/data"):
                graph.remove((None, None, None))
                return self._load_gsp(self._read())
            return self._send(200, "ok")

        # -------------------------------------------------------------- #
        def _run_query(self, q: str):
            try:
                res = graph.query(q)
            except Exception as exc:  # noqa: BLE001
                return self._send(400, f"query failed: {exc}")
            if res.type == "CONSTRUCT":
                return self._send(200, res.serialize(format="turtle"), "text/turtle")
            return self._send(200, res.serialize(format="json"),
                              "application/sparql-results+json")

        def _load_gsp(self, body: bytes):
            try:
                graph.parse(data=body.decode("utf-8", "replace"), format="turtle")
            except Exception as exc:  # noqa: BLE001
                return self._send(400, f"gsp load failed: {exc}")
            return self._send(200, "loaded")

    return Handler


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3030)
    parser.add_argument(
        "--ttl",
        default=str(Path(settings.kg_generated_dir) / "merged_kg.ttl"),
        help="Turtle file to seed the dataset (default: kg/generated/merged_kg.ttl).",
    )
    args = parser.parse_args(argv)

    graph = Graph()
    ttl = Path(args.ttl)
    if ttl.exists():
        graph.parse(str(ttl), format="turtle")
        info(f"Seeded {len(graph)} triples from {ttl}")
    else:
        warn(f"{ttl} not found; serving an empty graph (run `make demo` first).")

    handler = _build_handler(graph)
    info(f"Fuseki-compatible demo endpoint on http://localhost:{args.port}"
         f" (dataset: {settings.FUSEKI_DATASET})")
    info("Point the app at it with FUSEKI_BASE_URL=http://localhost:%d" % args.port)
    try:
        ThreadingHTTPServer(("0.0.0.0", args.port), handler).serve_forever()
    except KeyboardInterrupt:
        info("shutting down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
