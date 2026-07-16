"""Command-line entry point for deterministic PCA."""

import argparse
from pathlib import Path

from transcriptforge_analysis.pca import PCAConfig, run_pca


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PCA over an Expression Bundle.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    run_pca(arguments.bundle, PCAConfig.from_json(arguments.request), arguments.output_dir)


if __name__ == "__main__":
    main()
