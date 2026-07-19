"""Run a frozen TranscriptForge precision/reproducibility validation study."""

import argparse
import json
from pathlib import Path

from transcriptforge_analysis.input_degradation_study import (
    run_input_degradation_limit_study,
)
from transcriptforge_analysis.paired_bridging_study import run_paired_bridging_study
from transcriptforge_analysis.precision_study import run_precision_study
from transcriptforge_analysis.robustness_interference_study import (
    run_robustness_interference_study,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--study-spec", type=Path, required=True)
    parser.add_argument("--assignments", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    study_type = json.loads(arguments.study_spec.read_text(encoding="utf-8"))["study"]["type"]
    runner = {
        "INPUT_DEGRADATION_LIMIT": run_input_degradation_limit_study,
        "PAIRED_BRIDGING": run_paired_bridging_study,
        "ROBUSTNESS_INTERFERENCE": run_robustness_interference_study,
    }.get(study_type, run_precision_study)
    runner(
        arguments.bundle,
        arguments.model,
        arguments.model_manifest,
        arguments.study_spec,
        arguments.assignments,
        arguments.output_dir,
    )


if __name__ == "__main__":
    main()
