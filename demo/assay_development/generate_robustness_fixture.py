"""Generate deterministic inputs for a paired robustness/interference smoke study."""

import argparse
import json
from pathlib import Path

try:
    from demo.assay_development.generate_paired_bridge_fixture import generate as generate_bridge
except ModuleNotFoundError:
    from generate_paired_bridge_fixture import (
        generate as generate_bridge,  # type: ignore[import-not-found,no-redef]
    )


def generate(output_dir: Path) -> dict[str, str]:
    inputs = generate_bridge(output_dir)
    assignments = Path(inputs["study_assignments"])
    rows = assignments.read_text(encoding="utf-8").splitlines()
    header = rows[0].replace("\tinclude", "\tchallenge_type\tqc_failure\tinclude")
    updated = [header]
    for row in rows[1:]:
        if not row:
            continue
        fields = row.split("\t")
        is_challenge = fields[6] == "pipeline_b"
        updated.append("\t".join([*fields[:-1], "hemoglobin", "false", fields[-1]]))
        if not is_challenge:
            # The challenge type describes the intended pair and remains explicit on both rows.
            continue
    assignments.write_text("\n".join(updated) + "\n", encoding="utf-8")
    spec_path = Path(inputs["study_spec"])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    spec["study"].update(
        {
            "study_id": "robustness-interference-smoke-study",
            "name": "Hemoglobin interference workflow smoke study",
            "type": "ROBUSTNESS_INTERFERENCE",
            "objective": (
                "Quantify locked-endpoint changes under a prespecified hemoglobin challenge."
            ),
        }
    )
    spec["factors"] = [
        {"name": "condition", "type": "categorical", "treatment": "fixed"},
        {"name": "challenge_type", "type": "categorical", "treatment": "fixed"},
        {"name": "run", "type": "categorical", "treatment": "random"},
        {"name": "subgroup", "type": "categorical", "treatment": "fixed"},
    ]
    spec["endpoints"] = {
        "continuous": ["classifier_score", "mean_challenge_effect"],
        "categorical": ["predicted_class", "call_change_rate"],
        "qc": ["qc_failure"],
    }
    spec["analysis_plan"] = {
        "template": "paired_locked_endpoint_robustness_interference",
        "reference_condition": "pipeline_a",
        "challenge_condition": "pipeline_b",
        "maximum_effect_margin": 0.05,
        "condition_rationale": "Pipeline A is the unchallenged locked-endpoint reference.",
        "confidence_level": 0.95,
        "bootstrap_iterations": 200,
        "threshold_proximity_band": 0.1,
        "biological_specificity_claims_supported": False,
    }
    spec["acceptance_criteria"] = [
        {
            "key": "challenge_effect_margin",
            "metric": "mean_challenge_effect",
            "endpoint": "classifier_score",
            "operator": "absolute_lte",
            "threshold": 0.05,
            "rationale": "Absolute mean challenge effect must remain within margin.",
        },
        {
            "key": "call_change_rate",
            "metric": "call_change_rate",
            "endpoint": "predicted_class",
            "operator": "lte",
            "threshold": 0.05,
            "rationale": "Challenge-associated call changes must remain uncommon.",
        },
        {
            "key": "qc_failure_rate",
            "metric": "qc_failure_rate",
            "endpoint": "qc_failure",
            "operator": "lte",
            "threshold": 0.1,
            "rationale": "Challenge-associated QC failures must remain uncommon.",
        },
    ]
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return inputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    print(json.dumps(generate(parser.parse_args().output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
