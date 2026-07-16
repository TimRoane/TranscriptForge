"""Dimension-reduction suite and large demonstration tests."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from transcriptforge_analysis.dimension_reduction import (
    DimensionReductionConfig,
    run_dimension_reduction,
)
from transcriptforge_analysis.expression_bundle import BundleConfig, build_expression_bundle
from transcriptforge_analysis.matrix_validation import ValidationConfig

ROOT = Path(__file__).resolve().parents[3]


def _large_bundle(tmp_path: Path) -> Path:
    output = tmp_path / "large-bundle"
    build_expression_bundle(
        BundleConfig(
            validation=ValidationConfig.from_json(ROOT / "demo/large_experiment/validation.json"),
            prepared_dataset_id="prepared-large-test",
            prepared_version=1,
        ),
        output,
    )
    return output / "expression_bundle.tar.gz"


def _config(method: str) -> DimensionReductionConfig:
    return DimensionReductionConfig(
        analysis_id=f"analysis-{method}",
        prepared_dataset_id="prepared-large-test",
        method=method,  # type: ignore[arg-type]
        assay="log_expression",
        component_count=6,
        scale_features=False,
        top_variable_features=250,
        distance_metric="correlation",
        linkage_method="average",
        cluster_count=4,
        neighbors=12,
        min_distance=0.2,
        perplexity=15,
        random_seed=20260716,
    )


def _validate_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas/result_manifest.schema.json").read_text())
    Draft202012Validator(schema).validate(manifest)
    return dict(manifest)


def test_hierarchical_clustering_is_deterministic(tmp_path: Path) -> None:
    archive = _large_bundle(tmp_path)
    first = tmp_path / "clustering-first"
    second = tmp_path / "clustering-second"

    run_dimension_reduction(archive, _config("hierarchical_clustering"), first)
    run_dimension_reduction(archive, _config("hierarchical_clustering"), second)

    for filename in (
        "cluster_assignments.tsv",
        "linkage_matrix.tsv",
        "dendrogram_plot.json",
        "dendrogram_plot.svg",
        "correlation_heatmap.json",
        "correlation_heatmap.svg",
        "result_manifest.json",
        "report.qmd",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()
    manifest = _validate_manifest(first / "result_manifest.json")
    assert manifest["title"] == "Hierarchical sample clustering"
    assignments = (first / "cluster_assignments.tsv").read_text(encoding="utf-8")
    assert len(assignments.splitlines()) == 73


def test_umap_and_tsne_publish_repeatable_embedding_contracts(tmp_path: Path) -> None:
    archive = _large_bundle(tmp_path)
    for method in ("umap", "tsne"):
        first = tmp_path / f"{method}-first"
        second = tmp_path / f"{method}-second"
        run_dimension_reduction(archive, _config(method), first)
        run_dimension_reduction(archive, _config(method), second)

        assert (first / "coordinates.tsv").read_bytes() == (second / "coordinates.tsv").read_bytes()
        assert (first / "embedding_plot.json").read_bytes() == (
            second / "embedding_plot.json"
        ).read_bytes()
        assert (first / "embedding_plot.svg").read_bytes() == (
            second / "embedding_plot.svg"
        ).read_bytes()
        assert (first / "report.qmd").read_bytes() == (second / "report.qmd").read_bytes()
        _validate_manifest(first / "result_manifest.json")
        plot = json.loads((first / "embedding_plot.json").read_text(encoding="utf-8"))
        assert len(plot["points"]) == 72
        assert plot["points"][0]["metadata"]["treatment"] == "vehicle"
