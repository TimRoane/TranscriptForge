"""Run a frozen pre-lock TranscriptForge Development Experiment."""

import argparse
import json
from pathlib import Path

from transcriptforge_analysis.assay_experiment import (
    PAIRED_CONDITION_EXPERIMENT,
    SUPPORTED_EXPERIMENT,
    run_input_degradation_experiment,
    run_paired_condition_experiment,
)
from transcriptforge_analysis.multifactor_experiment import (
    MULTIFACTOR_EXPERIMENT,
    run_multifactor_experiment,
)
from transcriptforge_analysis.technical_feasibility_experiment import (
    TECHNICAL_FEASIBILITY_EXPERIMENT,
    run_technical_feasibility_experiment,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--assignments", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    experiment_type = json.loads(arguments.spec.read_text(encoding="utf-8"))["experiment"][
        "type"
    ]
    runners = {
        SUPPORTED_EXPERIMENT: run_input_degradation_experiment,
        PAIRED_CONDITION_EXPERIMENT: run_paired_condition_experiment,
        MULTIFACTOR_EXPERIMENT: run_multifactor_experiment,
        TECHNICAL_FEASIBILITY_EXPERIMENT: run_technical_feasibility_experiment,
    }
    if experiment_type not in runners:
        raise SystemExit(f"Unsupported Development Experiment type: {experiment_type}")
    runners[experiment_type](
        arguments.spec,
        arguments.assignments,
        arguments.bundle,
        arguments.output_dir,
    )


if __name__ == "__main__":
    main()
