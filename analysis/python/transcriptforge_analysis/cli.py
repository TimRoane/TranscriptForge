"""Thin command-line wrapper for matrix and metadata validation."""

import argparse
from dataclasses import replace
from pathlib import Path

from transcriptforge_analysis.matrix_validation import (
    ValidationConfig,
    build_dataset_manifest,
    validate_dataset,
    write_json_atomic,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ValidationConfig.from_json(args.config)
    if args.matrix is not None or args.metadata is not None:
        config = replace(
            config,
            matrix_path=args.matrix or config.matrix_path,
            metadata_path=args.metadata or config.metadata_path,
        )
    report = validate_dataset(config)
    write_json_atomic(args.output, report.to_dict())
    if report.status == "VALID" and args.manifest_output is not None:
        write_json_atomic(args.manifest_output, build_dataset_manifest(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
