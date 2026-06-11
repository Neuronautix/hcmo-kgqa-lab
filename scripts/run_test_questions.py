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
        data = data.get("questions", [])
    return data


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
    print(f"\n{'#':<3} {'intent':<24} {'ok':<4} {'rows':<6} question")
    print("-" * 72)
    for i, r in enumerate(results, 1):
        get = (lambda k, d=None: r.get(k, d)) if isinstance(r, dict) else (lambda k, d=None: getattr(r, k, d))
        print(
            f"{i:<3} {str(get('intent', '')):<24} "
            f"{str(get('ok', get('correct', '')))!s:<4} "
            f"{str(get('rows', get('row_count', ''))):<6} "
            f"{str(get('question', ''))[:40]}"
        )


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["template", "generated"], default="template")
    parser.add_argument("--provider", default=None)
    parser.add_argument(
        "--questions",
        default=str(Path(settings.REPO_ROOT) / "app" / "evaluation" / "test_questions.yaml"),
    )
    args = parser.parse_args(argv)

    questions = _load_questions(Path(args.questions))
    info(f"Loaded {len(questions)} question(s); mode={args.mode}")
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
    try:
        results = runner(questions, mode=args.mode, provider=args.provider)
    except TypeError:
        results = runner(questions)
    metrics = results.get("metrics") if isinstance(results, dict) else None
    rows = results.get("results") if isinstance(results, dict) else results
    _print_table(rows)
    if metrics:
        print("\nMetrics:")
        for k, v in metrics.items():
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
