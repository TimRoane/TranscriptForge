"""Deterministic signature-scoring scientific contract tests."""

import hashlib
import io
import json
import tarfile
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from transcriptforge_analysis.signature_scoring import (
    SignatureScoringConfig,
    run_signature_scoring,
)

ROOT = Path(__file__).parents[3]


def _bundle(path: Path) -> str:
    files = {
        "expression_bundle/bundle_manifest.json": json.dumps(
            {
                "assays": [{"name": "log_expression", "path": "assays/log_expression.tsv"}],
                "sample_metadata": "metadata/sample_metadata.tsv",
            }
        ).encode(),
        "expression_bundle/assays/log_expression.tsv": (
            b"feature_id\tsample_1\tsample_2\tsample_3\n"
            b"gene_1\t1\t2\t4\n"
            b"gene_2\t4\t2\t1\n"
            b"gene_3\t2\t2\t2\n"
            b"gene_4\t0\t3\t6\n"
        ),
        "expression_bundle/metadata/sample_metadata.tsv": (
            b"sample_id\tcondition\nsample_1\tcontrol\nsample_2\ttreated\nsample_3\ttreated\n"
        ),
    }
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            member.mtime = 0
            archive.addfile(member, io.BytesIO(payload))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config(method: str, bundle_sha256: str) -> SignatureScoringConfig:
    report = {
        "signature_definition_id": "definition-1",
        "signature_definition_sha256": "a" * 64,
        "expression_bundle_sha256": bundle_sha256,
        "mapping_coverage": 0.75,
        "requested_identifier_count": 4,
        "mapped_identifier_count": 3,
        "missing_identifier_count": 1,
        "ambiguous_identifier_count": 0,
        "duplicate_identifier_count": 0,
        "sets": [
            {
                "signature_id": "set-1",
                "name": "Treatment response",
                "requested_identifier_count": 4,
                "mapped_identifier_count": 3,
                "mapping_coverage": 0.75,
                "mapped_entries": [
                    {"identifier": "G1", "feature_id": "gene_1", "weight": 2.0},
                    {"identifier": "G2", "feature_id": "gene_2", "weight": -1.0},
                    {"identifier": "G3", "feature_id": "gene_3", "weight": 0.5},
                ],
            }
        ],
    }
    return SignatureScoringConfig(
        analysis_id="analysis-1",
        prepared_dataset_id="prepared-1",
        method=method,  # type: ignore[arg-type]
        assay="log_expression",
        mapping_id="mapping-1",
        mapping_report_sha256="b" * 64,
        mapping_report=report,
    )


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("mean_expression", [7 / 3, 2.0, 7 / 3]),
        ("weighted_linear", [-1.0, 3.0, 8.0]),
        ("rank_based", [0.75, 0.5, 0.5]),
    ],
)
def test_signature_scoring_methods_are_exact_and_reproducible(
    tmp_path: Path, method: str, expected: list[float]
) -> None:
    bundle = tmp_path / "bundle.tar.gz"
    digest = _bundle(bundle)
    first = tmp_path / "first"
    second = tmp_path / "second"
    summary = run_signature_scoring(bundle, _config(method, digest), first)
    run_signature_scoring(bundle, _config(method, digest), second)

    observed = [item["score"] for item in summary["sets"][0]["scores"]]
    assert observed == pytest.approx(expected)
    assert summary["signature_mapping"]["mapping_coverage"] == 0.75
    assert summary["warnings"] == ["Mapping report contains 1 missing identifier(s)."]
    assert {item.name: item.read_bytes() for item in first.iterdir()} == {
        item.name: item.read_bytes() for item in second.iterdir()
    }
    schema = json.loads((ROOT / "schemas/signature_scores.schema.json").read_text())
    Draft202012Validator(schema).validate(summary)


def test_mean_z_score_excludes_constant_features_and_records_final_features(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle.tar.gz"
    digest = _bundle(bundle)
    output = tmp_path / "scores"
    summary = run_signature_scoring(bundle, _config("mean_z_score", digest), output)

    matrix = np.asarray([[1.0, 2.0, 4.0], [4.0, 2.0, 1.0]])
    expected = np.mean(
        (matrix - np.mean(matrix, axis=1, keepdims=True))
        / np.std(matrix, axis=1, ddof=1, keepdims=True),
        axis=0,
    )
    observed = [item["score"] for item in summary["sets"][0]["scores"]]
    assert observed == pytest.approx(expected)
    assert summary["sets"][0]["scored_feature_count"] == 2
    assert summary["sets"][0]["excluded_constant_feature_count"] == 1
    features = (output / "scored_features.tsv").read_text()
    assert "gene_3\t0.5\tFALSE\tconstant_across_samples" in features
    assert any("excluded 1 constant" in item for item in summary["warnings"])
