"""Command-line entry point for canonical Expression Bundle construction."""

import argparse
from dataclasses import replace
from pathlib import Path

from transcriptforge_analysis.expression_bundle import BundleConfig, build_expression_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = BundleConfig.from_json(args.config)
    config = replace(
        config,
        validation=replace(
            config.validation,
            matrix_path=args.matrix,
            metadata_path=args.metadata,
        ),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    build_expression_bundle(config, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
