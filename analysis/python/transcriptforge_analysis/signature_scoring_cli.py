"""Command-line entry point for deterministic signature scoring."""

import argparse
from pathlib import Path

from transcriptforge_analysis.signature_scoring import (
    SignatureScoringConfig,
    run_signature_scoring,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    run_signature_scoring(
        arguments.bundle,
        SignatureScoringConfig.from_json(arguments.request),
        arguments.output_dir,
    )


if __name__ == "__main__":
    main()
