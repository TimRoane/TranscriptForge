"""Command-line entry point for locked TranscriptForge classifier inference."""

import argparse
from pathlib import Path

from transcriptforge_analysis.classifier_prediction import predict_with_model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    predict_with_model(arguments.bundle, arguments.model, arguments.output_dir)


if __name__ == "__main__":
    main()
