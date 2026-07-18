"""Evaluate one frozen external classifier prediction against sealed truth."""

import argparse
from pathlib import Path

from transcriptforge_analysis.external_classifier_evaluation import (
    evaluate_external_predictions,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    evaluate_external_predictions(args.predictions, args.truth, args.protocol, args.output_dir)


if __name__ == "__main__":
    main()
