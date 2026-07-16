"""Generate a deterministic paired multifactor RNA-seq demonstration study."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

SEED = 20_260_716
FEATURE_COUNT = 2_000
SUBJECTS_PER_STRATUM = 6


def generate(output_dir: Path) -> dict[str, Any]:
    """Write counts, metadata, and known simulated effects."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    samples = _sample_design()
    feature_ids = [f"ENSG{90_000_000_000 + index:011d}" for index in range(1, FEATURE_COUNT + 1)]

    baseline = rng.normal(np.log(85.0), 1.0, FEATURE_COUNT)
    treatment_effect = np.zeros(FEATURE_COUNT)
    treatment_effect[:150] = np.log(2) * 1.5
    treatment_effect[470:570] = np.log(2) * -1.2
    genotype_effect = np.zeros(FEATURE_COUNT)
    genotype_effect[150:270] = np.log(2) * 1.2
    interaction_effect = np.zeros(FEATURE_COUNT)
    interaction_effect[270:350] = np.log(2) * 1.8
    sex_effect = np.zeros(FEATURE_COUNT)
    sex_effect[430:470] = np.log(2) * 0.7
    batch_effects = {
        "batch_1": np.zeros(FEATURE_COUNT),
        "batch_2": np.r_[np.zeros(350), np.full(80, np.log(2) * 0.65), np.zeros(1570)],
        "batch_3": np.r_[np.zeros(350), np.full(80, np.log(2) * -0.55), np.zeros(1570)],
    }
    subject_effects = {
        sample["subject_id"]: rng.normal(0, 0.18, FEATURE_COUNT) for sample in samples
    }
    dispersions = rng.uniform(0.08, 0.22, FEATURE_COUNT)
    counts = np.empty((FEATURE_COUNT, len(samples)), dtype=np.int64)
    for sample_index, sample in enumerate(samples):
        log_mean = baseline.copy()
        if sample["treatment"] == "stimulated":
            log_mean += treatment_effect
        if sample["genotype"] == "variant":
            log_mean += genotype_effect
        if sample["genotype"] == "variant" and sample["treatment"] == "stimulated":
            log_mean += interaction_effect
        if sample["sex"] == "female":
            log_mean += sex_effect
        log_mean += batch_effects[sample["batch"]]
        log_mean += subject_effects[sample["subject_id"]]
        log_mean += float(sample["library_factor_log"])
        mean = np.exp(log_mean)
        shape = 1.0 / dispersions
        rate = rng.gamma(shape=shape, scale=mean / shape)
        counts[:, sample_index] = rng.poisson(rate)

    _write_metadata(output_dir / "sample_metadata.tsv", samples)
    _write_counts(output_dir / "counts.tsv", feature_ids, samples, counts)
    _write_ground_truth(output_dir / "ground_truth.tsv", feature_ids)
    summary = {
        "schema_version": "1.0.0",
        "seed": SEED,
        "sample_count": len(samples),
        "subject_count": len({sample["subject_id"] for sample in samples}),
        "feature_count": FEATURE_COUNT,
        "design": "~ batch + sex + genotype * treatment + subject_pair",
        "groups": {
            f"{genotype}_{treatment}": sum(
                sample["genotype"] == genotype and sample["treatment"] == treatment
                for sample in samples
            )
            for genotype in ("wild_type", "variant")
            for treatment in ("vehicle", "stimulated")
        },
        "known_effects": {
            "treatment_up": 150,
            "genotype_up": 120,
            "interaction_up": 80,
            "batch": 80,
            "sex": 40,
            "treatment_down": 100,
            "null": 1430,
        },
    }
    _write_json(output_dir / "experiment_summary.json", summary)
    return summary


def _sample_design() -> list[dict[str, str | float]]:
    samples: list[dict[str, str | float]] = []
    sample_number = 1
    subject_number = 1
    for batch in ("batch_1", "batch_2", "batch_3"):
        for genotype in ("wild_type", "variant"):
            for replicate in range(1, SUBJECTS_PER_STRATUM + 1):
                subject_id = f"donor_{subject_number:02d}"
                sex = "female" if replicate % 2 else "male"
                library_factor_log = ((subject_number % 7) - 3) * 0.035
                for treatment in ("vehicle", "stimulated"):
                    samples.append(
                        {
                            "sample_id": f"sample_{sample_number:03d}",
                            "subject_id": subject_id,
                            "genotype": genotype,
                            "treatment": treatment,
                            "batch": batch,
                            "sex": sex,
                            "timepoint": "24h",
                            "replicate": str(replicate),
                            "library_factor_log": library_factor_log,
                        }
                    )
                    sample_number += 1
                subject_number += 1
    return samples


def _write_metadata(path: Path, samples: list[dict[str, str | float]]) -> None:
    fields = (
        "sample_id",
        "subject_id",
        "genotype",
        "treatment",
        "batch",
        "sex",
        "timepoint",
        "replicate",
    )
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, delimiter="\t", fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for sample in samples:
            writer.writerow({field: sample[field] for field in fields})


def _write_counts(
    path: Path,
    feature_ids: list[str],
    samples: list[dict[str, str | float]],
    counts: np.ndarray[Any, Any],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(["gene_id", *(str(sample["sample_id"]) for sample in samples)])
        for feature_id, row in zip(feature_ids, counts, strict=True):
            writer.writerow([feature_id, *(str(int(value)) for value in row)])


def _write_ground_truth(path: Path, feature_ids: list[str]) -> None:
    effects = (
        (0, 150, "treatment_up", 1.5),
        (150, 270, "genotype_up", 1.2),
        (270, 350, "genotype_treatment_interaction", 1.8),
        (350, 430, "batch", 0.65),
        (430, 470, "sex", 0.7),
        (470, 570, "treatment_down", -1.2),
        (570, FEATURE_COUNT, "null_or_subject_noise", 0.0),
    )
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(["feature_id", "simulated_effect", "nominal_log2_fold_change"])
        for start, end, effect, fold_change in effects:
            for feature_id in feature_ids[start:end]:
                writer.writerow([feature_id, effect, fold_change])


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "data")
    arguments = parser.parse_args()
    summary = generate(arguments.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
