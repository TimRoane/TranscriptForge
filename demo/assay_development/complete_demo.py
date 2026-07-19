"""Generate the coherent, deterministic end-to-end assay-development demonstration."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

SEED = 20_260_718
FEATURE_COUNT = 2_000
FEATURE_IDS = tuple(f"ENSG{index:011d}" for index in range(1, FEATURE_COUNT + 1))

DATASET_NAMES = {
    "feasibility": "Paired FFPE feasibility series",
    "optimization": "Paired library-method optimization",
    "classifier": "Balanced classifier development cohort",
    "precision": "Crossed precision and reproducibility panel",
    "robustness": "Paired robustness challenge panel",
}

TRUTH_BLOCKS: dict[str, dict[str, Any]] = {
    "classifier_positive": {
        "features": list(FEATURE_IDS[0:40]),
        "expected_direction": "higher_in_case",
        "log_effect": 0.85,
    },
    "classifier_negative": {
        "features": list(FEATURE_IDS[40:80]),
        "expected_direction": "lower_in_case",
        "log_effect": -0.75,
    },
    "degradation_sensitive": {
        "features": list(FEATURE_IDS[80:140]),
        "expected_direction": "lower_at_reduced_input",
        "log_effect_at_25ng": -0.70,
    },
    "candidate_method_shift": {
        "features": list(FEATURE_IDS[140:180]),
        "expected_direction": "higher_with_candidate_method",
        "log_effect": 0.20,
    },
    "run_effect": {
        "features": list(FEATURE_IDS[180:220]),
        "expected_direction": "higher_on_run_b",
        "log_effect": 0.18,
    },
    "null": {
        "features": list(FEATURE_IDS[1_000:2_000]),
        "expected_direction": "none",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_metadata(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_counts(path: Path, rows: list[dict[str, str]], counts: np.ndarray) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(["gene_id", *[row["sample_id"] for row in rows]])
        for feature_id, values in zip(FEATURE_IDS, counts, strict=True):
            writer.writerow([feature_id, *values.tolist()])


def _base_expression(rng: np.random.Generator) -> np.ndarray:
    return rng.normal(np.log(180.0), 0.75, FEATURE_COUNT)


def _draw_counts(
    rng: np.random.Generator,
    log_means: Sequence[np.ndarray],
    *,
    dispersion: float = 0.06,
) -> np.ndarray:
    result = np.zeros((FEATURE_COUNT, len(log_means)), dtype=np.int64)
    size = 1.0 / dispersion
    for column, values in enumerate(log_means):
        means = np.exp(np.clip(values, -10, 12))
        result[:, column] = rng.negative_binomial(size, size / (size + means))
    return result


def _technical_effect(row: dict[str, str]) -> np.ndarray:
    effect = np.zeros(FEATURE_COUNT)
    if row.get("sequencing_run") == "run_b" or row.get("run") == "run_b":
        effect[180:220] = 0.18
    if row.get("operator") == "operator_2":
        effect[220:240] = -0.10
    if row.get("reagent_lot") == "lot_b":
        effect[240:260] = 0.10
    return effect


def _feasibility(
    rng: np.random.Generator, base: np.ndarray
) -> tuple[list[dict[str, str]], np.ndarray]:
    rows: list[dict[str, str]] = []
    means: list[np.ndarray] = []
    subject_effects = rng.normal(0, 0.16, (6, FEATURE_COUNT))
    input_effect = {100: 0.0, 50: -0.24, 25: -0.70}
    order = 1
    for subject in range(1, 7):
        for level_index, input_ng in enumerate((100, 50, 25)):
            row = {
                "sample_id": f"FFPE{subject:02d}_{input_ng}ng",
                "biological_sample_id": f"FFPE{subject:02d}",
                "input_ng": str(input_ng),
                "dv200": str({100: 74, 50: 59, 25: 43}[input_ng] - subject % 3),
                "sequencing_run": "run_a" if (subject + level_index) % 2 == 0 else "run_b",
                "operator": "operator_1" if (subject + level_index) % 2 == 0 else "operator_2",
                "reagent_lot": "lot_a" if (subject + 2 * level_index) % 2 == 0 else "lot_b",
                "instrument": f"sequencer_{1 + (subject + level_index) % 2}",
                "processing_order": str(order),
                "specimen_model": "synthetic_ffpe_tumor_rna",
            }
            effect = np.zeros(FEATURE_COUNT)
            effect[80:140] = input_effect[input_ng]
            means.append(base + subject_effects[subject - 1] + effect + _technical_effect(row))
            rows.append(row)
            order += 1
    return rows, _draw_counts(rng, means, dispersion=0.07)


def _optimization(
    rng: np.random.Generator, base: np.ndarray
) -> tuple[list[dict[str, str]], np.ndarray]:
    rows: list[dict[str, str]] = []
    means: list[np.ndarray] = []
    subject_effects = rng.normal(0, 0.18, (12, FEATURE_COUNT))
    order = 1
    for subject in range(1, 13):
        for method_index, condition in enumerate(("reference", "candidate")):
            row = {
                "sample_id": f"OPT{subject:02d}_{condition}",
                "biological_sample_id": f"OPT{subject:02d}",
                "pair_id": f"OPT{subject:02d}",
                "condition": condition,
                "library_method": condition,
                "sequencing_run": "run_a" if (subject + method_index) % 2 == 0 else "run_b",
                "operator": "operator_1" if (subject + method_index) % 2 == 0 else "operator_2",
                "reagent_lot": "lot_a" if (subject + 2 * method_index) % 2 == 0 else "lot_b",
                "quality_metric": str(56 + subject * 2),
                "processing_order": str(order),
            }
            effect = np.zeros(FEATURE_COUNT)
            if condition == "candidate":
                effect[140:180] = 0.20
            means.append(base + subject_effects[subject - 1] + effect + _technical_effect(row))
            rows.append(row)
            order += 1
    return rows, _draw_counts(rng, means)


def _classifier(
    rng: np.random.Generator, base: np.ndarray
) -> tuple[list[dict[str, str]], np.ndarray]:
    rows: list[dict[str, str]] = []
    means: list[np.ndarray] = []
    subject_effects = rng.normal(0, 0.20, (96, FEATURE_COUNT))
    for subject in range(1, 97):
        outcome = "case" if subject % 2 == 0 else "control"
        cohort = "development_a" if subject <= 48 else "development_b"
        row = {
            "sample_id": f"DEV{subject:03d}",
            "biological_sample_id": f"DEV{subject:03d}",
            "outcome": outcome,
            "patient_id": f"PAT{subject:03d}",
            "cohort": cohort,
            "sequencing_run": "run_a" if subject % 4 in {0, 1} else "run_b",
            "operator": "operator_1" if subject % 4 in {0, 1} else "operator_2",
            "reagent_lot": "lot_a" if subject % 4 in {0, 3} else "lot_b",
            "site": f"site_{1 + subject % 3}",
            "borderline": "true" if subject in {9, 18, 35, 44, 61, 70, 87, 96} else "false",
        }
        effect = np.zeros(FEATURE_COUNT)
        if outcome == "case":
            attenuation = 0.35 if row["borderline"] == "true" else 1.0
            effect[0:40] = 0.85 * attenuation
            effect[40:80] = -0.75 * attenuation
        elif row["borderline"] == "true":
            effect[0:40] = 0.85 * 0.55
            effect[40:80] = -0.75 * 0.55
        means.append(base + subject_effects[subject - 1] + effect + _technical_effect(row))
        rows.append(row)
    return rows, _draw_counts(rng, means, dispersion=0.05)


def _precision(
    rng: np.random.Generator, base: np.ndarray
) -> tuple[list[dict[str, str]], np.ndarray]:
    rows: list[dict[str, str]] = []
    means: list[np.ndarray] = []
    subject_effects = rng.normal(0, 0.22, (8, FEATURE_COUNT))
    combinations = (
        ("operator_1", "run_a", "lot_a"),
        ("operator_1", "run_b", "lot_b"),
        ("operator_2", "run_a", "lot_b"),
        ("operator_2", "run_b", "lot_a"),
    )
    for subject in range(1, 9):
        outcome = "case" if subject % 2 == 0 else "control"
        for replicate, (operator, run, lot) in enumerate(combinations, 1):
            row = {
                "sample_id": f"PREC{subject:02d}_R{replicate}",
                "biological_sample_id": f"PREC{subject:02d}",
                "replicate_id": f"R{replicate}",
                "outcome": outcome,
                "operator": operator,
                "run": run,
                "reagent_lot": lot,
                "instrument": f"instrument_{1 + replicate % 2}",
                "day": f"day_{1 + (subject + replicate) % 2}",
                "qc_failure": "false",
            }
            effect = np.zeros(FEATURE_COUNT)
            if outcome == "case":
                effect[0:40] = 0.85
                effect[40:80] = -0.75
            means.append(
                base
                + subject_effects[subject - 1]
                + effect
                + _technical_effect(row)
                + rng.normal(0, 0.025, FEATURE_COUNT)
            )
            rows.append(row)
    return rows, _draw_counts(rng, means, dispersion=0.035)


def _robustness(
    rng: np.random.Generator, base: np.ndarray
) -> tuple[list[dict[str, str]], np.ndarray]:
    rows: list[dict[str, str]] = []
    means: list[np.ndarray] = []
    subject_effects = rng.normal(0, 0.20, (12, FEATURE_COUNT))
    challenge_types = ("hemoglobin", "freeze_thaw", "low_dv200")
    for subject in range(1, 13):
        outcome = "case" if subject % 2 == 0 else "control"
        challenge_type = challenge_types[(subject - 1) % len(challenge_types)]
        for condition_index, condition in enumerate(("reference", "challenge")):
            row = {
                "sample_id": f"ROB{subject:02d}_{condition}",
                "biological_sample_id": f"ROB{subject:02d}",
                "outcome": outcome,
                "condition": condition,
                "challenge_type": challenge_type,
                "run": "run_a" if (subject + condition_index) % 2 == 0 else "run_b",
                "operator": "operator_1" if (subject + condition_index) % 2 == 0 else "operator_2",
                "reagent_lot": "lot_a" if (subject + 2 * condition_index) % 2 == 0 else "lot_b",
                "subgroup": "threshold_adjacent" if subject in {3, 4, 9, 10} else "stable",
                "qc_failure": "false",
            }
            effect = np.zeros(FEATURE_COUNT)
            if outcome == "case":
                effect[0:40] = 0.85
                effect[40:80] = -0.75
            if condition == "challenge":
                effect[260:280] = {"hemoglobin": -0.12, "freeze_thaw": -0.08, "low_dv200": -0.16}[
                    challenge_type
                ]
            means.append(base + subject_effects[subject - 1] + effect + _technical_effect(row))
            rows.append(row)
    return rows, _draw_counts(rng, means, dispersion=0.05)


def generate_complete_demo(output_dir: Path) -> dict[str, Any]:
    """Write all source datasets and return a stable generation manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    base = _base_expression(rng)
    builders = {
        "feasibility": _feasibility,
        "optimization": _optimization,
        "classifier": _classifier,
        "precision": _precision,
        "robustness": _robustness,
    }
    datasets: dict[str, Any] = {}
    for key, builder in builders.items():
        dataset_dir = output_dir / key
        dataset_dir.mkdir(parents=True, exist_ok=True)
        metadata, counts = builder(rng, base)
        metadata_path = dataset_dir / "sample_metadata.tsv"
        counts_path = dataset_dir / "counts.tsv"
        _write_metadata(metadata_path, metadata)
        _write_counts(counts_path, metadata, counts)
        datasets[key] = {
            "name": DATASET_NAMES[key],
            "measurement_count": len(metadata),
            "feature_count": FEATURE_COUNT,
            "files": {
                "counts.tsv": _sha256(counts_path),
                "sample_metadata.tsv": _sha256(metadata_path),
            },
        }

    truth = {
        "schema_version": "1.0.0",
        "synthetic": True,
        "research_use_only": True,
        "seed": SEED,
        "shared_feature_universe": list(FEATURE_IDS),
        "truth_blocks": TRUTH_BLOCKS,
        "scientific_boundary": (
            "All specimens, outcomes, effects, and acceptance evidence are synthetic. "
            "They demonstrate software behavior and do not establish clinical performance."
        ),
    }
    truth_path = output_dir / "synthetic_truth.json"
    truth_path.write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0.0",
        "generator_version": "complete-assay-demo-v1",
        "seed": SEED,
        "synthetic": True,
        "research_use_only": True,
        "feature_count": FEATURE_COUNT,
        "datasets": datasets,
        "truth_sha256": _sha256(truth_path),
    }
    manifest_path = output_dir / "generation_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".transcriptforge-demo/complete_assay/source"),
    )
    print(
        json.dumps(generate_complete_demo(parser.parse_args().output_dir), indent=2, sort_keys=True)
    )


if __name__ == "__main__":
    main()
