"""Command-line dispatcher for dimension-reduction analyses."""

import argparse
from pathlib import Path

from transcriptforge_analysis.dimension_reduction import (
    DimensionReductionConfig,
    run_dimension_reduction,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    run_dimension_reduction(
        arguments.bundle,
        DimensionReductionConfig.from_json(arguments.request),
        arguments.output_dir,
    )


if __name__ == "__main__":
    main()
