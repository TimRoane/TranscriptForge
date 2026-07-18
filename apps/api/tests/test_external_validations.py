"""API coverage for immutable classifier external-validation studies."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from httpx import AsyncClient

ROOT = Path(__file__).parents[3]
PROTOCOL = ROOT / "demo/classifier_external_validation/gse32646_protocol.json"
RESULT = ROOT / "demo/classifier_external_validation/gse32646_external_validation_result.json"


async def create_project(client: AsyncClient) -> str:
    response = await client.post(
        "/api/projects",
        json={"name": "Classifier validation", "description": "API test"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def metadata() -> dict[str, object]:
    return {
        "name": "GSE140494 to GSE32646 pCR validation",
        "description": "Prespecified external validation",
        "development_summary": {
            "sample_count": 91,
            "input_feature_count": 23963,
            "selected_feature_count": 500,
            "roc_auc": 0.6234271099744245,
            "roc_auc_lower": 0.5116223363774735,
            "roc_auc_upper": 0.7780881459058941,
            "pr_auc": 0.3360480525435074,
            "permutation_p_value": 0.0297029702970297,
        },
    }


def upload_files(
    result_payload: bytes | None = None,
) -> dict[str, tuple[str | None, bytes | str, str | None]]:
    return {
        "metadata": (None, json.dumps(metadata()), "application/json"),
        "protocol": (PROTOCOL.name, PROTOCOL.read_bytes(), "application/json"),
        "result": (
            RESULT.name,
            result_payload if result_payload is not None else RESULT.read_bytes(),
            "application/json",
        ),
    }


@pytest.mark.asyncio
async def test_import_list_read_and_download_external_validation(
    client: AsyncClient,
) -> None:
    project_id = await create_project(client)
    response = await client.post(
        f"/api/projects/{project_id}/classifier-external-validations",
        files=upload_files(),
    )
    assert response.status_code == 201, response.text
    study = response.json()
    assert study["project_id"] == project_id
    assert study["development_accession"] == "GSE140494"
    assert study["external_accession"] == "GSE32646"
    assert study["status"] == "SUCCESS_CRITERIA_NOT_MET"
    assert study["result"]["metrics"]["roc_auc"] == pytest.approx(0.6191077441)
    assert study["prediction_summary"] is None
    assert [artifact["name"] for artifact in study["artifacts"]] == ["protocol", "result"]
    assert all("storage_uri" not in artifact for artifact in study["artifacts"])

    listed = await client.get(
        f"/api/projects/{project_id}/classifier-external-validations"
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [study["id"]]

    detail = await client.get(f"/api/classifier-external-validations/{study['id']}")
    assert detail.status_code == 200
    assert detail.json()["protocol_id"] == "breast-pcr-gse140494-to-gse32646-v1"

    download = await client.get(
        f"/api/classifier-external-validations/{study['id']}/artifacts/result"
    )
    assert download.status_code == 200
    assert download.content == RESULT.read_bytes()
    assert download.headers["content-disposition"].endswith(
        'filename="gse32646_external_validation_result.json"'
    )

    duplicate = await client.post(
        f"/api/projects/{project_id}/classifier-external-validations",
        files=upload_files(),
    )
    assert duplicate.status_code == 409

    deleted = await client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204
    missing = await client.get(f"/api/classifier-external-validations/{study['id']}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_import_rejects_provenance_mismatch(client: AsyncClient) -> None:
    project_id = await create_project(client)
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    result["provenance"]["protocol_sha256"] = hashlib.sha256(b"other").hexdigest()
    response = await client.post(
        f"/api/projects/{project_id}/classifier-external-validations",
        files=upload_files((json.dumps(result) + "\n").encode()),
    )
    assert response.status_code == 422
    assert "protocol checksum" in response.json()["detail"].lower()

    listed = await client.get(
        f"/api/projects/{project_id}/classifier-external-validations"
    )
    assert listed.json() == []
