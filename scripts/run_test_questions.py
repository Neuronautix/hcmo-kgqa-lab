#!/usr/bin/env python3
"""Run the KGQA evaluation harness over the test-question set.

Reads ``app/evaluation/test_questions.yaml`` and runs each question through the
KGQA workflow (template-first by default), then prints a metrics table.

This script is defensive: the evaluation/workflow backend may still be under
construction. When a required module or the question file is absent it reports
the gap and exits cleanly rather than crashing.

Usage:
    python scripts/run_test_questions.py [--mode template|generated]
                                         [--provider NAME] [--questions PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import get_settings, info, warn


def _load_questions(path: Path):
    import yaml

    if not path.exists():
        warn(f"Question file not found: {path}")
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if isinstance(data, dict):
        if data.get("questions"):
            return data["questions"]
        # Curated competency-question set: normalize template -> expected_intent.
        if data.get("competency_questions"):
            return [
                {
                    "id": cq.get("id"),
                    "question": cq.get("question", ""),
                    "expected_intent": cq.get("template"),
                }
                for cq in data["competency_questions"]
            ]
        return []
    return data


def _resolve_provider(name, settings):
    """Build an LLM provider, optionally overriding the configured one by name."""
    from app.llm.provider import get_provider

    if not name:
        return get_provider(settings)
    try:
        s = settings.model_copy(update={"LLM_PROVIDER": name})
    except Exception:  # noqa: BLE001
        s = settings
    return get_provider(s)


def _find_runner():
    """Locate an evaluation entry point in app.evaluation, tolerantly."""
    try:
        import app.evaluation as ev  # noqa: F401
    except Exception:  # noqa: BLE001
        return None, None
    for modname in ("harness", "runner", "evaluate", "metrics"):
        try:
            mod = __import__(f"app.evaluation.{modname}", fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for fn in ("run_evaluation", "evaluate", "run", "run_test_questions"):
            f = getattr(mod, fn, None)
            if callable(f):
                return mod, f
    return None, None


def _print_table(results) -> None:
    if not results:
        info("No results to display.")
        return
    print(f"\n{'#':<3} {'P':<2} {'intent (pred / expected)':<40} {'rows':<5} question")
    print("-" * 92)
    for i, r in enumerate(results, 1):
        get = (lambda k, d=None: r.get(k, d)) if isinstance(r, dict) else (lambda k, d=None: getattr(r, k, d))
        pred = get("predicted_intent") or "-"
        exp = get("expected_intent") or "-"
        intent = f"{pred} / {exp}"
        rows = get("row_count")
        mark = "✓" if get("ok") else "✗"
        print(
            f"{i:<3} {mark:<2} {intent[:39]:<40} "
            f"{(str(rows) if rows is not None else '-'):<5} "
            f"{str(get('question', ''))[:38]}"
        )


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["template", "generated", "auto"], default="template")
    parser.add_argument("--provider", default=None)
    default_questions = Path(settings.REPO_ROOT) / "app" / "evaluation" / "test_questions.yaml"
    competency_set = Path(settings.REPO_ROOT) / "sparql" / "competency_questions.yaml"
    parser.add_argument("--questions", default=str(default_questions))
    parser.add_argument(
        "--competency", action="store_true",
        help="Evaluate the full curated competency-question set instead.",
    )
    parser.add_argument(
        "--no-execute", action="store_true",
        help="Skip Fuseki execution (offline: validate + build only).",
    )
    parser.add_argument("--report", default=None, help="Write the full JSON report to PATH.")
    args = parser.parse_args(argv)

    qpath = competency_set if args.competency else Path(args.questions)
    questions = _load_questions(qpath)
    info(f"Loaded {len(questions)} question(s) from {qpath.name}; mode={args.mode}")
    if not questions:
        warn("Nothing to evaluate (no questions). The evaluation set may not "
            "be authored yet.")
        return 0

    mod, runner = _find_runner()
    if runner is None:
        warn("No evaluation harness found in app.evaluation yet; printing the "
            "loaded questions only.")
        for i, q in enumerate(questions, 1):
            text = q.get("question") if isinstance(q, dict) else q
            print(f"  {i}. {text}")
        return 0

    info(f"Using evaluation entry point: {runner.__name__}")
    provider = _resolve_provider(args.provider, settings)
    try:
        results = runner(
            questions, mode=args.mode, provider=provider, execute=not args.no_execute
        )
    except TypeError:
        results = runner(questions)

    rows = results.get("records") if isinstance(results, dict) else results
    _print_table(rows)
    if isinstance(results, dict):
        metrics = results.get("metrics") or {}
        print(
            f"\nSummary: n={results.get('n')} mode={results.get('mode')} "
            f"pass_rate={results.get('pass_rate')}"
        )
        if metrics:
            print("Metrics:")
            for k, v in metrics.items():
                print(f"  {k}: {v:.3f}" if isinstance(v, float) else f"  {k}: {v}")
        if args.report:
            import json

            Path(args.report).write_text(
                json.dumps(results, indent=2, default=str), encoding="utf-8"
            )
            info(f"Wrote report to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
