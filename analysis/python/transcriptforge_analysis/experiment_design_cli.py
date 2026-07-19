"""Validate a Development Experiment design before expensive computation."""

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from transcriptforge_analysis.assay_experiment import (
    PAIRED_CONDITION_EXPERIMENT,
    read_assignments,
    read_paired_condition_assignments,
    validate_input_degradation_design,
    validate_paired_condition_design,
)
from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.multifactor_experiment import (
    MULTIFACTOR_EXPERIMENT,
    validate_multifactor_design,
)
from transcriptforge_analysis.technical_feasibility_experiment import (
    TECHNICAL_FEASIBILITY_EXPERIMENT,
    read_technical_feasibility_assignments,
    validate_technical_feasibility_design,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--assignments", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    spec = json.loads(arguments.spec.read_text(encoding="utf-8"))
    schema = json.loads(arguments.schema.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(spec), key=lambda error: list(error.path)
    )
    if errors:
        location = ".".join(str(value) for value in errors[0].path) or "document"
        raise SystemExit(f"ExperimentSpec is invalid at {location}: {errors[0].message}")
    result: Any
    if spec["experiment"]["type"] == TECHNICAL_FEASIBILITY_EXPERIMENT:
        result = validate_technical_feasibility_design(
            spec, read_technical_feasibility_assignments(arguments.assignments)
        )
    elif spec["experiment"]["type"] == PAIRED_CONDITION_EXPERIMENT:
        result = validate_paired_condition_design(
            spec, read_paired_condition_assignments(arguments.assignments)
        )
    elif spec["experiment"]["type"] == MULTIFACTOR_EXPERIMENT:
        result = validate_multifactor_design(
            spec, read_paired_condition_assignments(arguments.assignments)
        )
    else:
        result = validate_input_degradation_design(spec, read_assignments(arguments.assignments))
    write_json_atomic(arguments.output, result.to_dict())
    if not result.valid:
        codes = ", ".join(item.code for item in result.findings if item.severity == "ERROR")
        raise SystemExit(f"Experiment design is blocked: {codes}")


if __name__ == "__main__":
    main()
