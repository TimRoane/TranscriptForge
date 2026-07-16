"""Deterministic principal component analysis over an Expression Bundle."""

import csv
import gzip
import json
import shutil
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import numpy as np

from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.reporting import write_dimension_reduction_report
from transcriptforge_analysis.static_plots import write_scatter_svg, write_variance_svg


@dataclass(frozen=True, slots=True)
class PCAConfig:
    analysis_id: str
    prepared_dataset_id: str
    assay: str = "log_expression"
    component_count: int = 5
    scale_features: bool = False
    random_seed: int = 42

    @classmethod
    def from_json(cls, path: Path) -> "PCAConfig":
        payload = json.loads(path.read_text(encoding="utf-8"))
        parameters = payload.get("parameters", {})
        if payload.get("analysis_type") != "dimension_reduction":
            raise ValueError("PCA requires analysis_type 'dimension_reduction'.")
        if payload.get("method", "pca") != "pca":
            raise ValueError("This runner only supports the 'pca' method.")
        return cls(
            analysis_id=str(payload["analysis_id"]),
            prepared_dataset_id=str(payload["prepared_dataset_id"]),
            assay=str(payload["assay"]),
            component_count=int(parameters.get("component_count", 5)),
            scale_features=bool(parameters.get("scale_features", False)),
            random_seed=int(payload["random_seed"]),
        )


@dataclass(frozen=True, slots=True)
class PCAResult:
    sample_count: int
    feature_count: int
    component_count: int
    explained_variance_ratio: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class BundleAssay:
    feature_ids: list[str]
    sample_ids: list[str]
    matrix: np.ndarray[Any, Any]
    metadata: dict[str, dict[str, str]]


def load_bundle_assay(bundle_archive: Path, assay_name: str) -> BundleAssay:
    """Load one canonical assay and its aligned sample metadata into memory."""
    with _extracted_bundle(bundle_archive) as bundle:
        manifest = json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
        assay = next((item for item in manifest["assays"] if item["name"] == assay_name), None)
        if assay is None:
            raise ValueError(f"Assay '{assay_name}' is not present in the Expression Bundle.")
        feature_ids, sample_ids, matrix = _read_assay(bundle / str(assay["path"]))
        metadata = _read_metadata(bundle / str(manifest["sample_metadata"]), sample_ids)
    return BundleAssay(feature_ids, sample_ids, matrix, metadata)


def run_pca(bundle_archive: Path, config: PCAConfig, output_dir: Path) -> PCAResult:
    """Run centered SVD PCA and publish portable result contracts."""
    if config.component_count < 2:
        raise ValueError("PCA requires at least two requested components.")
    output_dir.mkdir(parents=True, exist_ok=False)
    bundle = load_bundle_assay(bundle_archive, config.assay)
    feature_ids = bundle.feature_ids
    sample_ids = bundle.sample_ids
    matrix = bundle.matrix
    metadata = bundle.metadata

    sample_matrix = matrix.T
    centered = sample_matrix - np.mean(sample_matrix, axis=0, keepdims=True)
    warnings: list[str] = []
    if config.scale_features:
        standard_deviation = np.std(centered, axis=0, ddof=1)
        constant = standard_deviation == 0
        if np.any(constant):
            warnings.append(
                f"{int(np.sum(constant))} constant feature(s) were retained "
                "with zero scaled values."
            )
            standard_deviation[constant] = 1.0
        centered = centered / standard_deviation

    left, singular_values, right_transposed = np.linalg.svd(centered, full_matrices=False)
    available = min(config.component_count, len(singular_values))
    coordinates = left[:, :available] * singular_values[:available]
    loadings = right_transposed[:available, :].T
    _canonicalize_component_signs(coordinates, loadings)
    denominator = max(len(sample_ids) - 1, 1)
    explained_variance = singular_values[:available] ** 2 / denominator
    total_variance = float(np.sum(singular_values**2 / denominator))
    if total_variance == 0:
        ratios = np.zeros(available, dtype=np.float64)
        warnings.append("All samples are identical after preprocessing; variance is zero.")
    else:
        ratios = explained_variance / total_variance

    component_names = [f"PC{index + 1}" for index in range(available)]
    _write_matrix_table(
        output_dir / "coordinates.tsv", "sample_id", sample_ids, component_names, coordinates
    )
    _write_matrix_table(
        output_dir / "loadings.tsv", "feature_id", feature_ids, component_names, loadings
    )
    _write_variance_table(
        output_dir / "explained_variance.tsv",
        component_names,
        explained_variance,
        ratios,
    )
    plot = {
        "schema_version": "1.0.0",
        "analysis_id": config.analysis_id,
        "axes": [
            {
                "component": name,
                "explained_variance_ratio": float(ratio),
            }
            for name, ratio in zip(component_names, ratios, strict=True)
        ],
        "points": [
            {
                "sample_id": sample_id,
                "coordinates": {
                    name: float(coordinates[row_index, column_index])
                    for column_index, name in enumerate(component_names)
                },
                "metadata": metadata[sample_id],
            }
            for row_index, sample_id in enumerate(sample_ids)
        ],
    }
    variance_plot = {
        "schema_version": "1.0.0",
        "components": [
            {
                "component": name,
                "explained_variance": float(variance),
                "explained_variance_ratio": float(ratio),
            }
            for name, variance, ratio in zip(
                component_names, explained_variance, ratios, strict=True
            )
        ],
    }
    write_json_atomic(output_dir / "pca_plot.json", plot)
    write_json_atomic(output_dir / "variance_plot.json", variance_plot)
    write_scatter_svg(
        output_dir / "pca_plot.svg",
        title="Principal component analysis",
        sample_ids=sample_ids,
        coordinates=coordinates,
        axis_names=component_names,
        metadata=metadata,
        axis_ratios=ratios,
    )
    write_variance_svg(output_dir / "variance_plot.svg", component_names, ratios)
    result_manifest = {
        "schema_version": "1.0.0",
        "analysis_type": "dimension_reduction",
        "title": "Principal component analysis",
        "summary_metrics": [
            {"label": "Samples", "value": len(sample_ids)},
            {"label": "Features", "value": len(feature_ids)},
            {"label": "Components", "value": available},
            {"label": "Assay", "value": config.assay},
            {"label": "Random seed", "value": config.random_seed},
        ],
        "sections": [
            {
                "id": "pca",
                "title": "Sample coordinates",
                "items": [
                    {"type": "plotly_json", "title": "PCA plot", "path": "pca_plot.json"},
                    {"type": "image", "title": "Static PCA plot", "path": "pca_plot.svg"},
                    {"type": "table", "title": "Coordinates", "path": "coordinates.tsv"},
                ],
            },
            {
                "id": "variance",
                "title": "Explained variance",
                "items": [
                    {
                        "type": "plotly_json",
                        "title": "Explained variance",
                        "path": "variance_plot.json",
                    },
                    {
                        "type": "image",
                        "title": "Static explained variance",
                        "path": "variance_plot.svg",
                    },
                    {"type": "table", "title": "Loadings", "path": "loadings.tsv"},
                ],
            },
        ],
        "downloads": [
            {"type": "table", "title": "PCA coordinates", "path": "coordinates.tsv"},
            {"type": "table", "title": "PCA loadings", "path": "loadings.tsv"},
            {
                "type": "table",
                "title": "Explained variance",
                "path": "explained_variance.tsv",
            },
            {"type": "image", "title": "PCA plot (SVG)", "path": "pca_plot.svg"},
            {
                "type": "image",
                "title": "Explained variance (SVG)",
                "path": "variance_plot.svg",
            },
            {"type": "html", "title": "PCA report", "path": "report.html"},
            {"type": "file", "title": "Quarto report source", "path": "report.qmd"},
        ],
        "warnings": warnings,
    }
    write_json_atomic(output_dir / "result_manifest.json", result_manifest)
    write_dimension_reduction_report(
        output_dir,
        title="Principal component analysis",
        analysis_id=config.analysis_id,
        assay=config.assay,
        summary={
            "Samples": len(sample_ids),
            "Features": len(feature_ids),
            "Components": available,
            "Random seed": config.random_seed,
        },
        images=(
            ("Sample coordinates", "pca_plot.svg"),
            ("Explained variance", "variance_plot.svg"),
        ),
        notes=tuple(
            f"{name} explains {float(ratio) * 100:.2f}% of total variance."
            for name, ratio in zip(component_names, ratios, strict=True)
        ),
    )
    return PCAResult(
        sample_count=len(sample_ids),
        feature_count=len(feature_ids),
        component_count=available,
        explained_variance_ratio=tuple(float(value) for value in ratios),
    )


@contextmanager
def _extracted_bundle(archive_path: Path) -> Iterator[Path]:
    temporary = Path(tempfile.mkdtemp(prefix="transcriptforge-pca-"))
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                destination = (temporary / member.name).resolve()
                if not destination.is_relative_to(temporary.resolve()):
                    raise ValueError("Expression Bundle contains an unsafe archive path.")
                if member.issym() or member.islnk():
                    raise ValueError("Expression Bundle may not contain links.")
            archive.extractall(temporary, filter="data")
        bundle = temporary / "expression_bundle"
        if not (bundle / "bundle_manifest.json").is_file():
            raise ValueError("Expression Bundle manifest is missing.")
        yield bundle
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _read_assay(path: Path) -> tuple[list[str], list[str], np.ndarray[Any, Any]]:
    feature_ids: list[str] = []
    values: list[list[float]] = []
    with _open_text(path) as source:
        reader = csv.reader(source, delimiter="\t")
        header = next(reader)
        if not header or header[0] != "feature_id":
            raise ValueError("Canonical assay must begin with a feature_id column.")
        sample_ids = header[1:]
        for row in reader:
            feature_ids.append(row[0])
            values.append([float(value) for value in row[1:]])
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape != (len(feature_ids), len(sample_ids)):
        raise ValueError("Canonical assay is not a rectangular feature-by-sample matrix.")
    if len(sample_ids) < 2 or len(feature_ids) < 2:
        raise ValueError("PCA requires at least two samples and two features.")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("PCA assay contains non-finite values.")
    return feature_ids, sample_ids, matrix


def _read_metadata(path: Path, expected_samples: list[str]) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        if reader.fieldnames is None or "sample_id" not in reader.fieldnames:
            raise ValueError("Sample metadata must contain sample_id.")
        rows = {str(row["sample_id"]): {str(k): str(v) for k, v in row.items()} for row in reader}
    missing = [sample for sample in expected_samples if sample not in rows]
    if missing:
        raise ValueError("Sample metadata is missing assay samples: " + ", ".join(missing[:5]))
    return {sample: rows[sample] for sample in expected_samples}


def _canonicalize_component_signs(
    coordinates: np.ndarray[Any, Any], loadings: np.ndarray[Any, Any]
) -> None:
    for component in range(loadings.shape[1]):
        pivot = int(np.argmax(np.abs(loadings[:, component])))
        if loadings[pivot, component] < 0:
            loadings[:, component] *= -1
            coordinates[:, component] *= -1


def _write_matrix_table(
    path: Path,
    id_column: str,
    row_ids: list[str],
    components: list[str],
    matrix: np.ndarray[Any, Any],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow([id_column, *components])
        for row_id, row in zip(row_ids, matrix, strict=True):
            writer.writerow([row_id, *(format(float(value), ".12g") for value in row)])


def _write_variance_table(
    path: Path,
    components: list[str],
    variances: np.ndarray[Any, Any],
    ratios: np.ndarray[Any, Any],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination, delimiter="\t", lineterminator="\n")
        writer.writerow(["component", "explained_variance", "explained_variance_ratio"])
        for name, variance, ratio in zip(components, variances, ratios, strict=True):
            writer.writerow([name, format(float(variance), ".12g"), format(float(ratio), ".12g")])


@contextmanager
def _open_text(path: Path) -> Iterator[TextIO]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
            yield source
    else:
        with path.open(encoding="utf-8", newline="") as source:
            yield source
