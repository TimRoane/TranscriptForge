"""Hierarchical clustering, UMAP, and t-SNE over Expression Bundles."""

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage  # type: ignore[import-untyped]
from scipy.spatial.distance import pdist  # type: ignore[import-untyped]

from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.pca import PCAConfig, load_bundle_assay, run_pca
from transcriptforge_analysis.reporting import write_dimension_reduction_report
from transcriptforge_analysis.static_plots import (
    write_dendrogram_svg,
    write_heatmap_svg,
    write_scatter_svg,
)

Method = Literal["pca", "hierarchical_clustering", "umap", "tsne"]


@dataclass(frozen=True, slots=True)
class DimensionReductionConfig:
    analysis_id: str
    prepared_dataset_id: str
    method: Method
    assay: str
    component_count: int
    scale_features: bool
    top_variable_features: int
    distance_metric: str
    linkage_method: str
    cluster_count: int
    neighbors: int
    min_distance: float
    perplexity: float
    random_seed: int

    @classmethod
    def from_json(cls, path: Path) -> "DimensionReductionConfig":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("analysis_type") != "dimension_reduction":
            raise ValueError("Dimension reduction requires its matching analysis type.")
        parameters = payload.get("parameters", {})
        method = str(payload.get("method", "pca"))
        supported = {"pca", "hierarchical_clustering", "umap", "tsne"}
        if method not in supported:
            raise ValueError(f"Unsupported dimension-reduction method '{method}'.")
        return cls(
            analysis_id=str(payload["analysis_id"]),
            prepared_dataset_id=str(payload["prepared_dataset_id"]),
            method=cast(Method, method),
            assay=str(payload["assay"]),
            component_count=int(parameters.get("component_count", 10)),
            scale_features=bool(parameters.get("scale_features", False)),
            top_variable_features=int(parameters.get("top_variable_features", 500)),
            distance_metric=str(parameters.get("distance_metric", "correlation")),
            linkage_method=str(parameters.get("linkage_method", "average")),
            cluster_count=int(parameters.get("cluster_count", 4)),
            neighbors=int(parameters.get("neighbors", 15)),
            min_distance=float(parameters.get("min_distance", 0.2)),
            perplexity=float(parameters.get("perplexity", 15)),
            random_seed=int(payload["random_seed"]),
        )


def run_dimension_reduction(
    bundle_archive: Path, config: DimensionReductionConfig, output_dir: Path
) -> None:
    """Dispatch a frozen request to its scientific implementation."""
    if config.method == "pca":
        run_pca(
            bundle_archive,
            PCAConfig(
                analysis_id=config.analysis_id,
                prepared_dataset_id=config.prepared_dataset_id,
                assay=config.assay,
                component_count=config.component_count,
                scale_features=config.scale_features,
                random_seed=config.random_seed,
            ),
            output_dir,
        )
        return
    bundle = load_bundle_assay(bundle_archive, config.assay)
    matrix, feature_ids = _prepare_matrix(
        bundle.matrix.T,
        bundle.feature_ids,
        config.top_variable_features,
        config.scale_features,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    if config.method == "hierarchical_clustering":
        _run_clustering(
            matrix,
            feature_ids,
            bundle.sample_ids,
            bundle.metadata,
            config,
            output_dir,
        )
    else:
        _run_embedding(
            matrix,
            feature_ids,
            bundle.sample_ids,
            bundle.metadata,
            config,
            output_dir,
        )


def _prepare_matrix(
    sample_matrix: np.ndarray[Any, Any],
    feature_ids: list[str],
    requested_features: int,
    scale_features: bool,
) -> tuple[np.ndarray[Any, Any], list[str]]:
    variances = np.var(sample_matrix, axis=0, ddof=1)
    variable = np.flatnonzero(variances > 0)
    if len(variable) < 2:
        raise ValueError("Dimension reduction requires at least two variable features.")
    ranked = variable[np.argsort(-variances[variable], kind="stable")]
    selected = ranked[: min(requested_features, len(ranked))]
    matrix = sample_matrix[:, selected].astype(np.float64, copy=True)
    matrix -= np.mean(matrix, axis=0, keepdims=True)
    if scale_features:
        standard_deviation = np.std(matrix, axis=0, ddof=1)
        standard_deviation[standard_deviation == 0] = 1.0
        matrix /= standard_deviation
    return matrix, [feature_ids[int(index)] for index in selected]


def _run_clustering(
    matrix: np.ndarray[Any, Any],
    feature_ids: list[str],
    sample_ids: list[str],
    metadata: dict[str, dict[str, str]],
    config: DimensionReductionConfig,
    output_dir: Path,
) -> None:
    if config.distance_metric not in {"euclidean", "correlation"}:
        raise ValueError("Clustering distance must be Euclidean or correlation.")
    if config.linkage_method not in {"average", "complete", "ward"}:
        raise ValueError("Unsupported hierarchical linkage method.")
    if config.linkage_method == "ward" and config.distance_metric != "euclidean":
        raise ValueError("Ward linkage requires Euclidean distance.")
    distances = pdist(matrix, metric=config.distance_metric)
    distances = np.nan_to_num(distances, nan=0.0, posinf=0.0, neginf=0.0)
    linkage_matrix = linkage(distances, method=config.linkage_method, optimal_ordering=True)
    tree = dendrogram(linkage_matrix, labels=sample_ids, no_plot=True)
    assignments = fcluster(linkage_matrix, config.cluster_count, criterion="maxclust")
    leaf_order = [int(index) for index in tree["leaves"]]
    ordered_samples = [sample_ids[index] for index in leaf_order]
    correlation = np.nan_to_num(np.corrcoef(matrix), nan=0.0)
    ordered_correlation = correlation[np.ix_(leaf_order, leaf_order)]

    _write_assignments(output_dir / "cluster_assignments.tsv", sample_ids, assignments)
    _write_linkage(output_dir / "linkage_matrix.tsv", linkage_matrix)
    write_json_atomic(
        output_dir / "dendrogram_plot.json",
        {
            "schema_version": "1.0.0",
            "analysis_id": config.analysis_id,
            "sample_order": ordered_samples,
            "icoord": tree["icoord"],
            "dcoord": tree["dcoord"],
            "color_list": tree["color_list"],
            "clusters": {
                sample_id: int(cluster)
                for sample_id, cluster in zip(sample_ids, assignments, strict=True)
            },
            "metadata": metadata,
        },
    )
    write_json_atomic(
        output_dir / "correlation_heatmap.json",
        {
            "schema_version": "1.0.0",
            "sample_order": ordered_samples,
            "values": ordered_correlation.tolist(),
            "metadata": metadata,
        },
    )
    write_dendrogram_svg(
        output_dir / "dendrogram_plot.svg",
        ordered_samples,
        tree["icoord"],
        tree["dcoord"],
    )
    write_heatmap_svg(
        output_dir / "correlation_heatmap.svg", ordered_samples, ordered_correlation
    )
    write_json_atomic(
        output_dir / "result_manifest.json",
        _clustering_manifest(config, len(sample_ids), len(feature_ids), assignments),
    )
    write_dimension_reduction_report(
        output_dir,
        title="Hierarchical sample clustering",
        analysis_id=config.analysis_id,
        assay=config.assay,
        summary={
            "Samples": len(sample_ids),
            "Variable features": len(feature_ids),
            "Clusters": len(set(int(value) for value in assignments)),
            "Distance": config.distance_metric,
            "Linkage": config.linkage_method,
        },
        images=(
            ("Sample dendrogram", "dendrogram_plot.svg"),
            ("Sample correlation heatmap", "correlation_heatmap.svg"),
        ),
        notes=("Branch height represents dissimilarity under the selected distance metric.",),
    )


def _clustering_manifest(
    config: DimensionReductionConfig,
    sample_count: int,
    feature_count: int,
    assignments: np.ndarray[Any, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "analysis_type": "dimension_reduction",
        "title": "Hierarchical sample clustering",
        "summary_metrics": [
            {"label": "Samples", "value": sample_count},
            {"label": "Variable features", "value": feature_count},
            {"label": "Clusters", "value": len(set(int(value) for value in assignments))},
            {"label": "Distance", "value": config.distance_metric},
            {"label": "Linkage", "value": config.linkage_method},
        ],
        "sections": [
            {
                "id": "dendrogram",
                "title": "Sample dendrogram",
                "items": [
                    {
                        "type": "plotly_json",
                        "title": "Dendrogram",
                        "path": "dendrogram_plot.json",
                    },
                    {
                        "type": "image",
                        "title": "Static dendrogram",
                        "path": "dendrogram_plot.svg",
                    },
                    {
                        "type": "table",
                        "title": "Cluster assignments",
                        "path": "cluster_assignments.tsv",
                    },
                ],
            },
            {
                "id": "correlation",
                "title": "Sample correlation",
                "items": [
                    {
                        "type": "plotly_json",
                        "title": "Correlation heatmap",
                        "path": "correlation_heatmap.json",
                    },
                    {
                        "type": "image",
                        "title": "Static correlation heatmap",
                        "path": "correlation_heatmap.svg",
                    },
                ],
            },
        ],
        "downloads": [
            {
                "type": "table",
                "title": "Cluster assignments",
                "path": "cluster_assignments.tsv",
            },
            {"type": "table", "title": "Linkage matrix", "path": "linkage_matrix.tsv"},
            {"type": "image", "title": "Dendrogram (SVG)", "path": "dendrogram_plot.svg"},
            {
                "type": "image",
                "title": "Correlation heatmap (SVG)",
                "path": "correlation_heatmap.svg",
            },
            {"type": "html", "title": "Clustering report", "path": "report.html"},
            {"type": "file", "title": "Quarto report source", "path": "report.qmd"},
        ],
        "warnings": [],
    }


def _run_embedding(
    matrix: np.ndarray[Any, Any],
    feature_ids: list[str],
    sample_ids: list[str],
    metadata: dict[str, dict[str, str]],
    config: DimensionReductionConfig,
    output_dir: Path,
) -> None:
    if config.method == "umap":
        from umap import UMAP  # type: ignore[import-untyped]

        if config.neighbors >= len(sample_ids):
            raise ValueError("UMAP neighbors must be smaller than the sample count.")
        model = UMAP(
            n_components=2,
            n_neighbors=config.neighbors,
            min_dist=config.min_distance,
            metric="euclidean",
            random_state=config.random_seed,
            transform_seed=config.random_seed,
            n_jobs=1,
        )
        coordinates = np.asarray(model.fit_transform(matrix), dtype=np.float64)
        axis_names = ["UMAP1", "UMAP2"]
        title = "Uniform manifold approximation and projection"
    else:
        from sklearn.manifold import TSNE  # type: ignore[import-untyped]

        if config.perplexity >= len(sample_ids):
            raise ValueError("t-SNE perplexity must be smaller than the sample count.")
        model = TSNE(
            n_components=2,
            perplexity=config.perplexity,
            init="pca",
            learning_rate="auto",
            max_iter=1_000,
            random_state=config.random_seed,
            method="barnes_hut",
        )
        coordinates = np.asarray(model.fit_transform(matrix), dtype=np.float64)
        axis_names = ["tSNE1", "tSNE2"]
        title = "t-distributed stochastic neighbor embedding"
    coordinates -= np.mean(coordinates, axis=0, keepdims=True)
    _canonicalize_axes(coordinates)
    _write_coordinates(output_dir / "coordinates.tsv", sample_ids, axis_names, coordinates)
    write_json_atomic(
        output_dir / "embedding_plot.json",
        {
            "schema_version": "1.0.0",
            "analysis_id": config.analysis_id,
            "method": config.method,
            "axes": axis_names,
            "points": [
                {
                    "sample_id": sample_id,
                    "coordinates": {
                        axis: float(coordinates[row, column])
                        for column, axis in enumerate(axis_names)
                    },
                    "metadata": metadata[sample_id],
                }
                for row, sample_id in enumerate(sample_ids)
            ],
        },
    )
    write_scatter_svg(
        output_dir / "embedding_plot.svg",
        title=f"{method_label(config.method)} sample coordinates",
        sample_ids=sample_ids,
        coordinates=coordinates,
        axis_names=axis_names,
        metadata=metadata,
    )
    write_json_atomic(
        output_dir / "result_manifest.json",
        _embedding_manifest(config, title, len(sample_ids), len(feature_ids)),
    )
    write_dimension_reduction_report(
        output_dir,
        title=title,
        analysis_id=config.analysis_id,
        assay=config.assay,
        summary={
            "Samples": len(sample_ids),
            "Variable features": len(feature_ids),
            "Method": method_label(config.method),
            "Random seed": config.random_seed,
        },
        images=((f"{method_label(config.method)} sample coordinates", "embedding_plot.svg"),),
        notes=(
            "Local neighborhoods are exploratory; global distances and axis orientation should "
            "not be over-interpreted.",
        ),
    )


def _embedding_manifest(
    config: DimensionReductionConfig, title: str, sample_count: int, feature_count: int
) -> dict[str, Any]:
    method_label = "UMAP" if config.method == "umap" else "t-SNE"
    metrics: list[dict[str, str | int | float]] = [
        {"label": "Samples", "value": sample_count},
        {"label": "Variable features", "value": feature_count},
        {"label": "Random seed", "value": config.random_seed},
    ]
    if config.method == "umap":
        metrics.extend(
            [
                {"label": "Neighbors", "value": config.neighbors},
                {"label": "Minimum distance", "value": config.min_distance},
            ]
        )
    else:
        metrics.append({"label": "Perplexity", "value": config.perplexity})
    return {
        "schema_version": "1.0.0",
        "analysis_type": "dimension_reduction",
        "title": title,
        "summary_metrics": metrics,
        "sections": [
            {
                "id": "embedding",
                "title": f"{method_label} sample coordinates",
                "items": [
                    {
                        "type": "plotly_json",
                        "title": f"{method_label} plot",
                        "path": "embedding_plot.json",
                    },
                    {
                        "type": "image",
                        "title": f"Static {method_label} plot",
                        "path": "embedding_plot.svg",
                    },
                ],
            }
        ],
        "downloads": [
            {"type": "table", "title": "Coordinates", "path": "coordinates.tsv"},
            {"type": "image", "title": f"{method_label} plot (SVG)", "path": "embedding_plot.svg"},
            {"type": "html", "title": f"{method_label} report", "path": "report.html"},
            {"type": "file", "title": "Quarto report source", "path": "report.qmd"},
        ],
        "warnings": [
            f"{method_label} is exploratory; global distances and axis orientation should not "
            "be over-interpreted."
        ],
    }


def _canonicalize_axes(coordinates: np.ndarray[Any, Any]) -> None:
    for axis in range(coordinates.shape[1]):
        pivot = int(np.argmax(np.abs(coordinates[:, axis])))
        if coordinates[pivot, axis] < 0:
            coordinates[:, axis] *= -1


def method_label(method: Method) -> str:
    return "UMAP" if method == "umap" else "t-SNE"


def _write_coordinates(
    path: Path,
    sample_ids: list[str],
    axis_names: list[str],
    coordinates: np.ndarray[Any, Any],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(["sample_id", *axis_names])
        for sample_id, row in zip(sample_ids, coordinates, strict=True):
            writer.writerow([sample_id, *(format(float(value), ".12g") for value in row)])


def _write_assignments(
    path: Path, sample_ids: list[str], assignments: np.ndarray[Any, Any]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(["sample_id", "cluster"])
        for sample_id, cluster in zip(sample_ids, assignments, strict=True):
            writer.writerow([sample_id, int(cluster)])


def _write_linkage(path: Path, matrix: np.ndarray[Any, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(["left", "right", "distance", "sample_count"])
        for row in matrix:
            writer.writerow([int(row[0]), int(row[1]), format(float(row[2]), ".12g"), int(row[3])])

