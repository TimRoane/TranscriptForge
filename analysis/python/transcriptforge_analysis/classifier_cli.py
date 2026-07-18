"""Command-line entry point for binary elastic-net classification."""

import argparse
import json
import os
from pathlib import Path

from transcriptforge_analysis.classifier import ClassifierConfig, run_classifier
from transcriptforge_analysis.multiclass_classifier import (
    MulticlassConfig,
    run_multiclass_classifier,
)


def _available_cpu_count() -> int:
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return os.cpu_count() or 1


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least one")
    return parsed


def _default_permutation_workers() -> int:
    configured = os.environ.get("TRANSCRIPTFORGE_CLASSIFIER_PERMUTATION_WORKERS")
    if configured is not None:
        return _positive_integer(configured)
    return min(8, _available_cpu_count())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--permutation-workers",
        type=_positive_integer,
        default=_default_permutation_workers(),
        help=(
            "Bounded process workers for independent binary label permutations "
            "(default: %(default)s)."
        ),
    )
    arguments = parser.parse_args()
    request = json.loads(arguments.request.read_text(encoding="utf-8"))
    if request.get("method") == "multinomial_elastic_net":
        run_multiclass_classifier(
            arguments.bundle,
            MulticlassConfig.from_json(arguments.request),
            arguments.output_dir,
        )
    else:
        run_classifier(
            arguments.bundle,
            ClassifierConfig.from_json(arguments.request),
            arguments.output_dir,
            permutation_workers=arguments.permutation_workers,
        )


if __name__ == "__main__":
    main()
