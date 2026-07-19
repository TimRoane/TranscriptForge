"""Generate a deterministic synthetic FFPE RNA input/degradation study."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

SEED = 20_260_718
BIOLOGICAL_SAMPLE_COUNT = 6
INPUT_LEVELS = (100, 50, 25)
FEATURE_COUNT = 500


def sample_design() -> list[dict[str, str]]:
    rows = []
    order = 1
    for sample_index in range(1, BIOLOGICAL_SAMPLE_COUNT + 1):
        biological_id = f"ffpe_{sample_index:02d}"
        run = "run_a" if sample_index % 2 else "run_b"
        operator = "operator_1" if sample_index <= 3 else "operator_2"
        for input_ng in INPUT_LEVELS:
            rows.append(
                {
                    "sample_id": f"{biological_id}_{input_ng}ng",
                    "biological_sample_id": biological_id,
                    "input_ng": str(input_ng),
                    "dv200": str({100: 72, 50: 58, 25: 43}[input_ng] - sample_index % 3),
                    "sequencing_run": run,
                    "operator": operator,
                    "reagent_lot": "lot_a" if sample_index in {1, 2, 5} else "lot_b",
                    "instrument": "sequencer_demo_1",
                    "processing_order": str(order),
                    "specimen_model": "synthetic_ffpe_tumor_rna",
                }
            )
            order += 1
    return rows


def generate(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    design = sample_design()
    baseline = rng.normal(np.log(140), 0.9, FEATURE_COUNT)
    biological_effects = rng.normal(0, 0.14, (BIOLOGICAL_SAMPLE_COUNT, FEATURE_COUNT))
    counts = np.zeros((FEATURE_COUNT, len(design)), dtype=np.int64)
    noise_by_input = {100: 0.025, 50: 0.075, 25: 0.19}
    dropout_by_input = {100: 0.0, 50: 0.002, 25: 0.025}
    for column, row in enumerate(design):
        biological_index = int(row["biological_sample_id"].split("_")[-1]) - 1
        input_ng = int(row["input_ng"])
        log_mean = baseline + biological_effects[biological_index]
        log_mean += rng.normal(0, noise_by_input[input_ng], FEATURE_COUNT)
        mean = np.exp(log_mean) * (0.95 + input_ng / 2000)
        observed = rng.negative_binomial(1 / 0.08, (1 / 0.08) / (1 / 0.08 + mean))
        dropout = rng.random(FEATURE_COUNT) < dropout_by_input[input_ng]
        observed[dropout] = 0
        counts[:, column] = observed

    metadata_path = output_dir / "sample_metadata.tsv"
    with metadata_path.open("w", encoding="utf-8", newline="") as destination:
        metadata_writer = csv.DictWriter(
            destination,
            fieldnames=list(design[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        metadata_writer.writeheader()
        metadata_writer.writerows(design)
    with (output_dir / "counts.tsv").open("w", encoding="utf-8", newline="") as destination:
        matrix_writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        matrix_writer.writerow(["gene_id", *[row["sample_id"] for row in design]])
        for feature_index, values in enumerate(counts, start=1):
            matrix_writer.writerow(
                [f"ENSG{80_000_000_000 + feature_index:011d}", *values.tolist()]
            )
    summary = {
        "schema_version": "1.0.0",
        "seed": SEED,
        "synthetic": True,
        "biological_sample_count": BIOLOGICAL_SAMPLE_COUNT,
        "measurement_count": len(design),
        "feature_count": FEATURE_COUNT,
        "input_levels_ng": list(INPUT_LEVELS),
        "intended_behavior": (
            "Increasing feature noise and dropout at lower input while retaining paired "
            "biological structure; all effects are synthetic and known by construction."
        ),
    }
    (output_dir / "study_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parent / "data"
    )
    print(json.dumps(generate(parser.parse_args().output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
