"""Deterministic PCA result-contract tests."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from transcriptforge_analysis.expression_bundle import BundleConfig, build_expression_bundle
from transcriptforge_analysis.matrix_validation import ValidationConfig
from transcriptforge_analysis.pca import PCAConfig, run_pca

ROOT = Path(__file__).resolve().parents[3]


def _bundle(tmp_path: Path) -> Path:
    output = tmp_path / "bundle-output"
    build_expression_bundle(
        BundleConfig(
            validation=ValidationConfig.from_json(
                ROOT / "demo/configs/count_matrix_validation.json"
            ),
            prepared_dataset_id="prepared-pca-test",
            prepared_version=1,
        ),
        output,
    )
    return output / "expression_bundle.tar.gz"


def test_pca_outputs_are_deterministic_and_schema_valid(tmp_path: Path) -> None:
    archive = _bundle(tmp_path)
    config = PCAConfig(
        analysis_id="analysis-pca-test",
        prepared_dataset_id="prepared-pca-test",
        component_count=3,
        random_seed=101,
    )
    first = tmp_path / "first"
    second = tmp_path / "second"

    result = run_pca(archive, config, first)
    run_pca(archive, config, second)

    assert result.sample_count == 4
    assert result.feature_count == 5
    assert result.component_count == 3
    assert sum(result.explained_variance_ratio) <= 1.000000000001
    for filename in (
        "coordinates.tsv",
        "loadings.tsv",
        "explained_variance.tsv",
        "pca_plot.json",
        "pca_plot.svg",
        "variance_plot.json",
        "variance_plot.svg",
        "result_manifest.json",
        "report.html",
        "report.qmd",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()

    manifest = json.loads((first / "result_manifest.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/result_manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    plot = json.loads((first / "pca_plot.json").read_text(encoding="utf-8"))
    assert [point["sample_id"] for point in plot["points"]] == [
        "sample_A",
        "sample_B",
        "sample_C",
        "sample_D",
    ]
    assert plot["points"][0]["metadata"]["condition"] == "control"
    assert "format:" in (first / "report.qmd").read_text(encoding="utf-8")
    assert "Research use only" in (first / "report.qmd").read_text(encoding="utf-8")
