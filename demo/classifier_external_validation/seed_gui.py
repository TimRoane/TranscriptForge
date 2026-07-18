#!/usr/bin/env python3
"""Idempotently import the completed GSE140494/GSE32646 study into the GUI."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_ID = "breast-pcr-gse140494-to-gse32646-v1"
PROJECT_NAME = "Breast pCR Classifier Validation"

ARTIFACTS = {
    "protocol": ROOT / "demo/classifier_external_validation/gse32646_protocol.json",
    "result": ROOT
    / "demo/classifier_external_validation/gse32646_external_validation_result.json",
    "development_results": ROOT
    / ".transcriptforge-demo/classifier_external_validation/GSE140494/classifier"
    / "classifier_results.json",
    "model": ROOT
    / ".transcriptforge-demo/classifier_external_validation/GSE140494/classifier/model.json",
    "prediction": ROOT
    / ".transcriptforge-demo/classifier_external_validation/GSE32646/prediction/results"
    / "prediction_results.json",
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base",
        default=os.getenv("TRANSCRIPTFORGE_API_BASE", "http://localhost:8000/api"),
    )
    parser.add_argument(
        "--web-base",
        default=os.getenv("TRANSCRIPTFORGE_WEB_BASE", "http://localhost:5173"),
    )
    return parser.parse_args()


def request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise SystemExit(
            f"GUI seed request failed ({response.status_code} {path}): {response.text}"
        ) from error
    return response


def main() -> None:
    options = arguments()
    missing = [str(path.relative_to(ROOT)) for path in ARTIFACTS.values() if not path.is_file()]
    if missing:
        raise SystemExit(
            "The completed Phase 9 artifacts must be materialized before GUI seeding. Missing:\n- "
            + "\n- ".join(missing)
            + "\nSee demo/classifier_external_validation/README.md."
        )

    api_base = options.api_base.rstrip("/")
    with httpx.Client(base_url=api_base, timeout=60) as client:
        projects = request(client, "GET", "/projects").json()
        project = next((item for item in projects if item["name"] == PROJECT_NAME), None)
        if project is None:
            project = request(
                client,
                "POST",
                "/projects",
                json={
                    "name": PROJECT_NAME,
                    "description": (
                        "Locked GSE140494 development and one-shot GSE32646 external "
                        "validation of a breast pathological-complete-response classifier."
                    ),
                },
            ).json()

        validations = request(
            client,
            "GET",
            f"/projects/{project['id']}/classifier-external-validations",
        ).json()
        existing = next(
            (item for item in validations if item["protocol_id"] == PROTOCOL_ID), None
        )
        if existing is not None:
            dashboard = (
                f"{options.web_base.rstrip('/')}/classifier-external-validations/"
                f"{existing['id']}"
            )
            print(f"Study already seeded: {dashboard}")
            return

        development = json.loads(ARTIFACTS["development_results"].read_text(encoding="utf-8"))
        roc_interval = development["confidence_intervals"]["intervals"]["roc_auc"]
        permutation = development.get("permutation_control")
        metadata = {
            "name": "GSE140494 → GSE32646 breast pCR classifier validation",
            "description": (
                "Prospectively frozen, single-use external evaluation across institutions, "
                "countries, biopsy workflows, and chemotherapy regimens."
            ),
            "development_summary": {
                "sample_count": development["sample_count"],
                "input_feature_count": development["input_feature_count"],
                "selected_feature_count": development["top_variable_features"],
                "roc_auc": development["metrics"]["roc_auc"],
                "roc_auc_lower": roc_interval["lower"],
                "roc_auc_upper": roc_interval["upper"],
                "pr_auc": development["metrics"]["pr_auc"],
                "permutation_p_value": (
                    permutation.get("empirical_p_value") if permutation else None
                ),
            },
        }
        files = {
            "metadata": (None, json.dumps(metadata), "application/json"),
            **{
                name: (path.name, path.read_bytes(), "application/json")
                for name, path in ARTIFACTS.items()
            },
        }
        study = request(
            client,
            "POST",
            f"/projects/{project['id']}/classifier-external-validations",
            files=files,
        ).json()

    print(f"Project: {options.web_base.rstrip('/')}/projects/{project['id']}")
    print(
        "External validation dashboard: "
        f"{options.web_base.rstrip('/')}/classifier-external-validations/{study['id']}"
    )


if __name__ == "__main__":
    main()
