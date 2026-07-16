"""Seed the multifactor demonstration through the public TranscriptForge API."""

import argparse
import json
import mimetypes
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_NAME = "TranscriptForge Visualization Study"
DATASET_NAME = "Paired genotype-treatment RNA-seq"
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}


class APIClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request) as response:
                if response.status == 204:
                    return None
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"API {method} {path} failed ({error.code}): {detail}") from error

    def upload(self, dataset_id: str, role: str, path: Path) -> dict[str, Any]:
        boundary = f"transcriptforge-{uuid4().hex}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = b"".join(
            (
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="role"\r\n\r\n',
                f"{role}\r\n--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                path.read_bytes(),
                f"\r\n--{boundary}--\r\n".encode(),
            )
        )
        request = urllib.request.Request(
            self.base_url + f"/datasets/{dataset_id}/files",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                return dict(json.load(response))
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"Upload failed ({error.code}): {detail}") from error


def _named(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((item for item in items if item["name"] == name), None)


def _wait_for_run(client: APIClient, run_id: str, label: str) -> dict[str, Any]:
    for _ in range(180):
        run = dict(client.request("GET", f"/runs/{run_id}"))
        print(f"{label}: {run['state']}")
        if run["state"] in TERMINAL_STATES:
            if run["state"] != "SUCCEEDED":
                raise RuntimeError(f"{label} failed: {run.get('error_summary') or run['state']}")
            return run
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {label.lower()}.")


def seed(client: APIClient, data_dir: Path) -> dict[str, Any]:
    projects = list(client.request("GET", "/projects"))
    project = _named(projects, PROJECT_NAME)
    if project is None:
        project = dict(
            client.request(
                "POST",
                "/projects",
                {
                    "name": PROJECT_NAME,
                    "description": (
                        "Deterministic 2 x 2 genotype-treatment study with paired donors "
                        "and three processing batches."
                    ),
                },
            )
        )
    datasets = list(client.request("GET", f"/projects/{project['id']}/datasets"))
    dataset = _named(datasets, DATASET_NAME)
    if dataset is None:
        dataset = dict(
            client.request(
                "POST",
                f"/projects/{project['id']}/datasets",
                {
                    "name": DATASET_NAME,
                    "description": "72 libraries, 36 paired donors, 2,000 simulated genes.",
                    "modality": "bulk_rnaseq",
                    "source_kind": "count_matrix",
                    "genome_build": "GRCh38",
                    "annotation_release": "synthetic-v1",
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
            _wait_for_run(client, validation["id"], "Validation")
        preparation = dict(client.request("POST", f"/datasets/{dataset['id']}/prepare"))
        completed = _wait_for_run(client, preparation["id"], "Preparation")
        prepared_id = str(completed["prepared_dataset_id"])
    else:
        prepared_id = str(prepared[0]["id"])

    specifications = (
        (
            "pca",
            "Multifactor experiment PCA",
            {"component_count": 10, "scale_features": False},
        ),
        (
            "hierarchical_clustering",
            "Multifactor experiment clustering",
            {
                "top_variable_features": 500,
                "distance_metric": "correlation",
                "linkage_method": "average",
                "cluster_count": 4,
            },
        ),
        (
            "umap",
            "Multifactor experiment UMAP",
            {"top_variable_features": 500, "neighbors": 15, "min_distance": 0.15},
        ),
        (
            "tsne",
            "Multifactor experiment t-SNE",
            {"top_variable_features": 500, "perplexity": 18},
        ),
    )
    saved_analyses = list(client.request("GET", f"/prepared-datasets/{prepared_id}/analyses"))
    analysis_urls: dict[str, str] = {}
    for method, name, parameters in specifications:
        analysis = _named(saved_analyses, name)
        if analysis is None:
            analysis = dict(
                client.request(
                    "POST",
                    f"/prepared-datasets/{prepared_id}/analyses",
                    {
                        "name": name,
                        "description": (
                            f"{method} view of the paired genotype-treatment demonstration study."
                        ),
                        "method": method,
                        "assay": "log_expression",
                        "parameters": parameters,
                        "random_seed": 20260716,
                    },
                )
            )
            saved_analyses.append(analysis)
        runs = list(client.request("GET", f"/analyses/{analysis['id']}/runs"))
        if not any(run["state"] == "SUCCEEDED" for run in runs):
            analysis_run = dict(client.request("POST", f"/analyses/{analysis['id']}/run"))
            _wait_for_run(client, analysis_run["id"], method.upper())
        analysis_urls[method] = f"http://localhost:5173/analyses/{analysis['id']}"
    return {
        "project_id": str(project["id"]),
        "dataset_id": str(dataset["id"]),
        "prepared_dataset_id": prepared_id,
        "project_url": f"http://localhost:5173/projects/{project['id']}",
        "prepared_dataset_url": f"http://localhost:5173/prepared-datasets/{prepared_id}",
        "analysis_urls": analysis_urls,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost:8000/api")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent / "data")
    arguments = parser.parse_args()
    if not (arguments.data_dir / "counts.tsv").is_file():
        raise SystemExit("Generate the large demo first with: make generate-large-demo")
    result = seed(APIClient(arguments.api_base), arguments.data_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
