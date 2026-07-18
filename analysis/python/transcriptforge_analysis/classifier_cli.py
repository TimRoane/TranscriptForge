"""Command-line entry point for binary elastic-net classification."""

import argparse
import json
from pathlib import Path

from transcriptforge_analysis.classifier import ClassifierConfig, run_classifier
from transcriptforge_analysis.multiclass_classifier import (
    MulticlassConfig,
    run_multiclass_classifier,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
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
        )


if __name__ == "__main__":
    main()
