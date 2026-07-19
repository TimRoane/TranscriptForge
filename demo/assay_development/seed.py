"""Seed the guided synthetic FFPE assay-development project through the public API."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from demo.assay_development.generate import generate
from demo.large_experiment.seed import APIClient, _named, _wait_for_run

PROJECT_NAME = "Synthetic FFPE Assay Development"
DATASET_NAME = "Paired FFPE RNA input series"
ASSAY_NAME = "Synthetic FFPE expression endpoint"
EXPERIMENT_NAME = "Blocked input-by-run design exercise"


def _metadata(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def seed(client: APIClient, data_dir: Path) -> dict[str, Any]:
    generate(data_dir)
    project = _named(list(client.request("GET", "/projects")), PROJECT_NAME)
    if project is None:
        project = dict(
            client.request(
                "POST",
                "/projects",
                {
                    "name": PROJECT_NAME,
                    "description": (
                        "Deterministic synthetic six-specimen FFPE RNA input/degradation "
                        "study for guided assay-development review."
                    ),
                },
            )
        )
    dataset = _named(
        list(client.request("GET", f"/projects/{project['id']}/datasets")), DATASET_NAME
    )
    if dataset is None:
        dataset = dict(
            client.request(
                "POST",
                f"/projects/{project['id']}/datasets",
                {
                    "name": DATASET_NAME,
                    "description": "18 paired synthetic measurements across 100, 50, and 25 ng.",
                    "modality": "bulk_rnaseq",
                    "source_kind": "count_matrix",
                    "genome_build": "GRCh38",
                    "annotation_release": "synthetic-ffpe-v1",
                },
            )
        )
    prepared = list(client.request("GET", f"/datasets/{dataset['id']}/prepared-versions"))
    if not prepared:
        if dataset["status"] in {"draft", "invalid"}:
            client.upload(dataset["id"], "count_matrix", data_dir / "counts.tsv")
            client.upload(dataset["id"], "sample_metadata", data_dir / "sample_metadata.tsv")
            validation = dict(
                client.request(
                    "POST",
                    f"/datasets/{dataset['id']}/validate",
                    {
                        "matrix_orientation": "features_by_samples",
                        "feature_id_column": "gene_id",
                        "sample_id_column": "sample_id",
                        "feature_id_type": "ensembl_gene_id",
                    },
                )
            )
            _wait_for_run(client, validation["id"], "FFPE validation")
        preparation = dict(client.request("POST", f"/datasets/{dataset['id']}/prepare"))
        completed = _wait_for_run(client, preparation["id"], "FFPE preparation")
        prepared_id = str(completed["prepared_dataset_id"])
    else:
        prepared_id = str(prepared[0]["id"])

    assay_projects = list(client.request("GET", "/assay-projects"))
    assay = next((item for item in assay_projects if item["project_id"] == project["id"]), None)
    if assay is None:
        assay = dict(
            client.request(
                "POST",
                "/assay-projects",
                {
                    "project_id": project["id"],
                    "name": ASSAY_NAME,
                    "proposed_purpose": (
                        "Explore whether lower RNA input or poorer quality destabilizes a "
                        "research expression endpoint before classifier development."
                    ),
                    "specimen_type": "synthetic FFPE tumor RNA",
                    "biological_context": "Known simulated paired input/degradation series.",
                    "proposed_output": "research expression endpoint stability",
                    "current_stage": "FEASIBILITY",
                    "assay_version": "development-unlocked",
                },
            )
        )
    questions = list(client.request("GET", f"/assay-projects/{assay['id']}/questions"))
    question = next(
        (item for item in questions if item["question_key"] == "input_degradation_stability"),
        None,
    )
    if question is None:
        question = dict(
            client.request(
                "POST",
                f"/assay-projects/{assay['id']}/questions",
                {
                    "question_key": "input_degradation_stability",
                    "formal_question": (
                        "Can 50 ng or 25 ng remain candidate development conditions while "
                        "paired expression stability and detected-gene behavior remain "
                        "interpretable?"
                    ),
                    "source": "USER_SELECTED",
                },
            )
        )
    experiments = list(client.request("GET", f"/assay-projects/{assay['id']}/experiments"))
    experiment = _named(experiments, EXPERIMENT_NAME)
    if experiment is None:
        assignments = []
        for row in _metadata(data_dir / "sample_metadata.tsv"):
            assignments.append(
                {
                    "measurement_id": row["sample_id"],
                    "biological_sample_id": row["biological_sample_id"],
                    "prepared_dataset_id": prepared_id,
                    "include": True,
                    "replicate_id": row["input_ng"],
                    "pair_id": row["biological_sample_id"],
                    "input_ng": float(row["input_ng"]),
                    "dv200": float(row["dv200"]),
                    "sequencing_run": f"run_input_{row['input_ng']}",
                    "operator": row["operator"],
                    "reagent_lot": row["reagent_lot"],
                    "instrument": row["instrument"],
                    "processing_order": int(row["processing_order"]),
                }
            )
        experiment = dict(
            client.request(
                "POST",
                "/experiments",
                {
                    "assay_project_id": assay["id"],
                    "question_id": question["id"],
                    "prepared_dataset_id": prepared_id,
                    "name": EXPERIMENT_NAME,
                    "objective": "Detect and repair input-by-run confounding before exploration.",
                    "experiment_type": "INPUT_DEGRADATION_EXPLORATION",
                    "mode": "ANALYZE_EXISTING",
                    "reference_level": 100,
                    "assay": "log_expression",
                    "declared_questions": [
                        "Does paired profile stability remain interpretable through 25 ng?"
                    ],
                    "reference_level_rationale": "100 ng is the highest tested input condition.",
                    "endpoint_rationale": (
                        "Paired profile correlation and detected genes characterize the "
                        "known simulated degradation response."
                    ),
                    "assignments": assignments,
                },
            )
        )
    return {
        "project_id": project["id"],
        "prepared_dataset_id": prepared_id,
        "assay_project_id": assay["id"],
        "experiment_id": experiment["id"],
        "experiment_status": experiment["status"],
        "assay_url": f"http://localhost:5173/assay-development/{assay['id']}",
        "experiment_url": f"http://localhost:5173/experiments/{experiment['id']}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost:8000/api")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=(
            Path(__file__).resolve().parents[2]
            / ".transcriptforge-demo/assay_development/source"
        ),
    )
    arguments = parser.parse_args()
    result = seed(APIClient(arguments.api_base), arguments.data_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
