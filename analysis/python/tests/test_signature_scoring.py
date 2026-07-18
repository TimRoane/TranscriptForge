"""Deterministic signature-scoring scientific contract tests."""

import hashlib
import io
import json
import tarfile
from dataclasses import replace
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


def _association_bundle(path: Path) -> str:
    files = {
        "expression_bundle/bundle_manifest.json": json.dumps(
            {
                "assays": [{"name": "log_expression", "path": "assays/log_expression.tsv"}],
                "sample_metadata": "metadata/sample_metadata.tsv",
            }
        ).encode(),
        "expression_bundle/assays/log_expression.tsv": (
            b"feature_id\tcontrol_1\tcontrol_2\tcontrol_3\ttreated_1\ttreated_2\ttreated_3\n"
            b"gene_1\t1\t1.2\t1.4\t4\t4.2\t4.4\n"
            b"gene_2\t4\t3.9\t3.8\t1\t0.9\t0.8\n"
            b"gene_3\t2\t2\t2\t2\t2\t2\n"
            b"gene_4\t0\t0\t0\t6\t6\t6\n"
        ),
        "expression_bundle/metadata/sample_metadata.tsv": (
            b"sample_id\tcondition\tdose\n"
            b"control_1\tcontrol\t0\ncontrol_2\tcontrol\t1\ncontrol_3\tcontrol\t2\n"
            b"treated_1\ttreated\t0\ntreated_2\ttreated\t1\ntreated_3\ttreated\t2\n"
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
    assert "must not be compared across RNA-seq" in summary["warnings"][0]
    assert summary["warnings"][1:] == ["Mapping report contains 1 missing identifier(s)."]
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


def test_signature_scores_include_adjusted_categorical_phenotype_association(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle.tar.gz"
    digest = _association_bundle(bundle)
    output = tmp_path / "scores"
    config = replace(
        _config("weighted_linear", digest),
        phenotype_column="condition",
        phenotype_kind="categorical",
    )

    summary = run_signature_scoring(bundle, config, output)

    association = summary["phenotype_association"]
    assert association["formula"] == "score ~ condition"
    result = association["associations"][0]
    assert result["test"] == "adjusted_two_group_comparison"
    assert result["effect"] == pytest.approx(9.0)
    assert [item["level"] for item in result["group_summaries"]] == ["control", "treated"]
    assert [item["sample_count"] for item in result["group_summaries"]] == [3, 3]
    assert [item["score_mean"] for item in result["group_summaries"]] == pytest.approx(
        [-0.5, 8.5]
    )
    assert 0 <= result["p_value"] <= 1
    assert (output / "signature_associations.tsv").is_file()
    assert "Scores by condition" in (output / "signature_associations.svg").read_text()
    schema = json.loads((ROOT / "schemas/signature_scores.schema.json").read_text())
    Draft202012Validator(schema).validate(summary)


def test_numeric_phenotype_association_adjusts_for_a_categorical_covariate(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle.tar.gz"
    digest = _association_bundle(bundle)
    output = tmp_path / "scores"
    config = replace(
        _config("weighted_linear", digest),
        phenotype_column="dose",
        phenotype_kind="numeric",
        covariates=("condition",),
    )

    summary = run_signature_scoring(bundle, config, output)

    association = summary["phenotype_association"]
    assert association["formula"] == "score ~ condition + dose"
    result = association["associations"][0]
    assert result["test"] == "adjusted_linear_regression"
    assert result["effect"] == pytest.approx(0.5)
    assert -1 <= result["correlation"] <= 1
    assert result["group_summaries"] == []
