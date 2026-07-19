"""Locked-model precision/reproducibility study and Validation Bundle builder."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from transcriptforge_analysis.classifier_prediction import predict_with_model
from transcriptforge_analysis.matrix_validation import write_json_atomic

CONTRACT_ROOT = Path(
    os.environ.get(
        "TRANSCRIPTFORGE_VALIDATION_CONTRACT_ROOT",
        Path(__file__).parents[3] / "contracts" / "validation",
    )
)


def run_precision_study(
    bundle: Path,
    model: Path,
    model_manifest: Path,
    study_spec: Path,
    assignments_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Apply one locked model once, then quantify prespecified repeated-measure evidence."""
    spec = json.loads(study_spec.read_text(encoding="utf-8"))
    _validate_spec(spec, model_manifest)
    assignments = _read_tsv(assignments_path)
    _validate_assignments(assignments, spec)
    output_dir.mkdir(parents=True, exist_ok=False)
    prediction_dir = output_dir / "_locked_prediction"
    prediction = predict_with_model(bundle, model, prediction_dir, model_manifest)
    prediction_by_sample = {row["sample_id"]: row for row in prediction["predictions"]}
    included = [row for row in assignments if _boolean(row.get("include", "true"))]
    assignment_ids = [row["measurement_id"] for row in included]
    if set(assignment_ids) != set(prediction_by_sample):
        missing = sorted(set(assignment_ids) - set(prediction_by_sample))
        extra = sorted(set(prediction_by_sample) - set(assignment_ids))
        raise ValueError(
            f"Study assignments and prediction samples disagree; missing={missing[:5]}, "
            f"unexpected={extra[:5]}."
        )
    endpoints = []
    for row in included:
        predicted = prediction_by_sample[row["measurement_id"]]
        if "positive_probability" in predicted:
            score = float(predicted["positive_probability"])
        else:
            score = float(max(predicted["class_probabilities"].values()))
        endpoints.append(
            {
                **row,
                "classifier_score": score,
                "predicted_class": predicted["predicted_class"],
            }
        )
    metrics = _metrics(
        endpoints, float(spec["analysis_plan"]["threshold_proximity_band"]), prediction
    )
    criteria = _evaluate_criteria(spec["acceptance_criteria"], metrics)
    overall = (
        "FAIL"
        if any(item["status"] == "FAIL" for item in criteria)
        else "INDETERMINATE"
        if any(item["status"] in {"INDETERMINATE", "NOT_APPLICABLE"} for item in criteria)
        else "PASS"
    )
    bundle_dir = output_dir / "validation_bundle"
    _write_bundle(
        bundle_dir,
        spec,
        assignments,
        endpoints,
        metrics,
        criteria,
        overall,
        model_manifest,
        bundle,
        model,
    )
    manifest = _manifest(bundle_dir, spec, overall)
    write_json_atomic(bundle_dir / "manifest.json", manifest)
    archive = output_dir / "validation_bundle.tar.gz"
    _archive(bundle_dir, archive)
    shutil.rmtree(prediction_dir)
    return {
        "study_id": spec["study"]["study_id"],
        "overall_status": overall,
        "metrics": metrics,
        "acceptance_results": criteria,
        "bundle_sha256": _sha(archive),
    }


def _validate_spec(spec: dict[str, Any], model_manifest_path: Path) -> None:
    schema = json.loads((CONTRACT_ROOT / "study_spec.schema.json").read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(spec), key=lambda error: list(error.path)
    )
    if errors:
        location = ".".join(str(value) for value in errors[0].path) or "document"
        raise ValueError(f"StudySpec violates its contract at {location}: {errors[0].message}")
    if spec["study"]["type"] != "PRECISION_REPRODUCIBILITY":
        raise ValueError("The precision runner only accepts PRECISION_REPRODUCIBILITY studies.")
    manifest_sha = _sha(model_manifest_path)
    if spec["model"]["manifest_sha256"] != manifest_sha:
        raise ValueError("StudySpec model manifest checksum does not match the locked input.")
    manifest = json.loads(model_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model_id") != spec["model"]["model_id"]:
        raise ValueError("StudySpec model identity does not match the locked ModelManifest.")


def _validate_assignments(assignments: list[dict[str, str]], spec: dict[str, Any]) -> None:
    required = {"measurement_id", "biological_sample_id", "replicate_id", "include"}
    required.update(factor["name"] for factor in spec["factors"])
    if not assignments:
        raise ValueError("Study assignments are empty.")
    missing = sorted(required - set(assignments[0]))
    if missing:
        raise ValueError(f"Study assignments lack required column(s): {', '.join(missing)}.")
    identifiers = [row["measurement_id"] for row in assignments]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Study measurement identifiers must be unique.")
    included = [row for row in assignments if _boolean(row["include"])]
    repeated = Counter(row["biological_sample_id"] for row in included)
    if len(repeated) < 2 or any(count < 2 for count in repeated.values()):
        raise ValueError(
            "Precision studies require at least two biological samples and two included "
            "measurements per sample."
        )
    for factor in spec["factors"]:
        levels = {row[factor["name"]] for row in included}
        if len(levels) < 2:
            raise ValueError(
                f"Precision factor '{factor['name']}' requires at least two observed levels."
            )


def _metrics(
    rows: list[dict[str, Any]], proximity_band: float, prediction: dict[str, Any]
) -> dict[str, Any]:
    scores = np.asarray([float(row["classifier_score"]) for row in rows])
    grouped: dict[str, list[float]] = defaultdict(list)
    calls: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[row["biological_sample_id"]].append(float(row["classifier_score"]))
        calls[row["biological_sample_id"]].append(str(row["predicted_class"]))
    within_variances = [
        float(np.var(values, ddof=1)) for values in grouped.values() if len(values) > 1
    ]
    repeatability_variance = float(np.mean(within_variances)) if within_variances else float("nan")
    biological_means = np.asarray([np.mean(values) for values in grouped.values()])
    mean_replicates = float(np.mean([len(values) for values in grouped.values()]))
    between_observed = float(np.var(biological_means, ddof=1)) if len(biological_means) > 1 else 0.0
    between_variance = max(0.0, between_observed - repeatability_variance / mean_replicates)
    total_variance = between_variance + repeatability_variance
    icc = between_variance / total_variance if total_variance > 0 else None
    stable = 0
    total_pairs = 0
    per_sample = []
    for sample_id, values in calls.items():
        counts = Counter(values)
        agreement = max(counts.values()) / len(values)
        stable += sum(count * (count - 1) // 2 for count in counts.values())
        total_pairs += len(values) * (len(values) - 1) // 2
        per_sample.append(
            {"biological_sample_id": sample_id, "agreement": agreement, "calls": counts}
        )
    categorical_agreement = stable / total_pairs if total_pairs else None
    threshold = float(prediction.get("decision_threshold", 0.5))
    near = [
        row for row in rows if abs(float(row["classifier_score"]) - threshold) <= proximity_band
    ]
    return {
        "precision": {
            "measurement_count": len(rows),
            "biological_sample_count": len(grouped),
            "mean": float(np.mean(scores)),
            "sd": float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0,
            "cv": float(np.std(scores, ddof=1) / np.mean(scores))
            if len(scores) > 1 and np.mean(scores)
            else None,
            "repeatability_sd": float(np.sqrt(repeatability_variance)),
            "reproducibility_sd": float(np.sqrt(total_variance)),
            "within_sample_ranges": {
                key: max(value) - min(value) for key, value in grouped.items()
            },
        },
        "variance_components": {
            "biological_sample": between_variance,
            "repeatability_residual": repeatability_variance,
            "total": total_variance,
            "icc": icc,
            "estimation": "balanced one-way random-effects method of moments",
        },
        "agreement": {
            "categorical_agreement": categorical_agreement,
            "per_sample_call_stability": per_sample,
        },
        "threshold_stability": {
            "decision_threshold": threshold,
            "proximity_band": proximity_band,
            "near_threshold_count": len(near),
            "near_threshold_measurement_ids": [row["measurement_id"] for row in near],
        },
    }


def _evaluate_criteria(
    criteria: list[dict[str, Any]], metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    lookup = {
        "icc": metrics["variance_components"]["icc"],
        "categorical_agreement": metrics["agreement"]["categorical_agreement"],
        "repeatability_sd": metrics["precision"]["repeatability_sd"],
        "reproducibility_sd": metrics["precision"]["reproducibility_sd"],
    }
    results = []
    for criterion in criteria:
        expected_endpoint = {
            "icc": "classifier_score",
            "categorical_agreement": "predicted_class",
            "repeatability_sd": "classifier_score",
            "reproducibility_sd": "classifier_score",
        }.get(criterion["metric"])
        observed = lookup.get(criterion["metric"])
        status = (
            "NOT_APPLICABLE"
            if expected_endpoint is None or criterion["endpoint"] != expected_endpoint
            else _criterion_status(observed, criterion["operator"], criterion["threshold"])
        )
        results.append(
            {
                **criterion,
                "observed": observed,
                "status": status,
                "population": "all included measurements",
                "uncertainty": None,
            }
        )
    return results


def _criterion_status(observed: float | None, operator: str, threshold: Any) -> str:
    if observed is None or not np.isfinite(observed):
        return "INDETERMINATE"
    if operator not in {"gt", "gte", "lt", "lte", "absolute_lte", "between"}:
        return "NOT_APPLICABLE"
    operations = {
        "gt": observed > float(threshold),
        "gte": observed >= float(threshold),
        "lt": observed < float(threshold),
        "lte": observed <= float(threshold),
        "absolute_lte": abs(observed) <= float(threshold),
        "between": isinstance(threshold, list)
        and len(threshold) == 2
        and float(threshold[0]) <= observed <= float(threshold[1]),
    }
    return "PASS" if operations.get(operator, False) else "FAIL"


def _write_bundle(
    root: Path,
    spec: dict[str, Any],
    assignments: list[dict[str, str]],
    endpoints: list[dict[str, Any]],
    metrics: dict[str, Any],
    criteria: list[dict[str, Any]],
    overall: str,
    model_manifest: Path,
    expression_bundle: Path,
    model: Path,
) -> None:
    for directory in (
        "design",
        "endpoints",
        "metrics",
        "figures",
        "decision",
        "provenance/nextflow_metadata",
        "report",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "study_spec.yaml").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    shutil.copyfile(model_manifest, root / "model_manifest.json")
    _write_tsv(root / "design/study_assignments.tsv", assignments)
    write_json_atomic(root / "design/design_validation.json", spec["design_validation"])
    _factor_balance(root / "design/factor_balance.tsv", endpoints, spec["factors"])
    _confounding(root / "design/confounding_matrix.tsv", endpoints, spec["factors"])
    _write_endpoint_tables(root / "endpoints", endpoints)
    excluded = [row for row in assignments if not _boolean(row.get("include", "true"))]
    _write_tsv(root / "endpoints/excluded_measurements.tsv", excluded)
    for name, payload in (
        ("precision_metrics", metrics["precision"]),
        ("variance_components", metrics["variance_components"]),
        ("agreement_metrics", metrics["agreement"]),
        ("threshold_stability", metrics["threshold_stability"]),
        ("acceptance_results", {"overall_status": overall, "criteria": criteria}),
    ):
        write_json_atomic(root / f"metrics/{name}.json", payload)
    summary = {
        "study_id": spec["study"]["study_id"],
        "question": spec["study"]["objective"],
        "overall_status": overall,
        "finding": (
            f"Prespecified criteria resolved to {overall}; individual results remain visible."
        ),
        "criteria": criteria,
        "limitations": [
            "Research-use validation evidence only; acceptance criteria are scientist-declared.",
            "A locked model was applied without retraining.",
        ],
        "scientist_decision_required": True,
    }
    write_json_atomic(root / "decision/decision_summary.json", summary)
    (root / "decision/decision_summary.md").write_text(
        f"# Validation decision summary\n\n**Overall:** {overall}\n\n{summary['finding']}\n"
    )
    write_json_atomic(
        root / "decision/recommendations.json",
        {"recommendations": [{"action": "SCIENTIST_REVIEW", "launch_automatically": False}]},
    )
    write_json_atomic(
        root / "decision/unresolved_questions.json", {"questions": summary["limitations"]}
    )
    _provenance(root / "provenance", expression_bundle, model, model_manifest, spec)
    _report(root / "report", spec, summary, metrics)


def _write_endpoint_tables(directory: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("Precision study has no included endpoints.")
    fields = list(rows[0])
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as stream:
        text = io.TextIOWrapper(stream, encoding="utf-8", newline="", write_through=True)
        writer = csv.DictWriter(text, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        text.detach()
    (directory / "endpoint_table.tsv.gz").write_bytes(raw.getvalue())
    pq.write_table(
        pa.Table.from_pylist(rows), directory / "endpoint_table.parquet", compression="zstd"
    )


def _factor_balance(path: Path, rows: list[dict[str, Any]], factors: list[dict[str, Any]]) -> None:
    output: list[dict[str, Any]] = []
    for factor in factors:
        counts = Counter(str(row.get(factor["name"], "")) for row in rows)
        output.extend(
            {"factor": factor["name"], "level": level, "count": count}
            for level, count in sorted(counts.items())
        )
    _write_tsv(path, output)


def _confounding(path: Path, rows: list[dict[str, Any]], factors: list[dict[str, Any]]) -> None:
    output: list[dict[str, Any]] = []
    for left_index, left in enumerate(factors):
        for right in factors[left_index + 1 :]:
            cells = Counter(
                (str(row.get(left["name"], "")), str(row.get(right["name"], ""))) for row in rows
            )
            output.append(
                {
                    "left_factor": left["name"],
                    "right_factor": right["name"],
                    "observed_cells": len(cells),
                    "perfect_alignment": len(cells)
                    == max(len({a for a, _ in cells}), len({b for _, b in cells})),
                }
            )
    _write_tsv(path, output)


def _provenance(
    root: Path, bundle: Path, model: Path, manifest: Path, spec: dict[str, Any]
) -> None:
    model_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    (root / "input_checksums.tsv").write_text(
        "role\tsha256\n"
        + "\n".join(
            f"{role}\t{_sha(path)}"
            for role, path in (
                ("expression_bundle", bundle),
                ("model", model),
                ("model_manifest", manifest),
            )
        )
        + "\n"
    )
    (root / "software_versions.yml").write_text(
        "transcriptforge: 0.1.0\npython: deterministic-runtime\n"
    )
    (root / "container_digests.tsv").write_text(
        "process\tcontainer_digest\n"
        f"locked_model_prediction\t{model_manifest.get('container_digest', 'not-recorded')}\n"
    )
    write_json_atomic(root / "parameters.json", spec["analysis_plan"])
    (root / "nextflow_metadata/README.txt").write_text(
        "Nextflow trace/report/timeline/DAG are indexed beside this bundle.\n"
    )


def _report(
    root: Path, spec: dict[str, Any], summary: dict[str, Any], metrics: dict[str, Any]
) -> None:
    root.joinpath("validation_report.html").write_text(
        "<!doctype html><html><body><h1>TranscriptForge Validation Study</h1>"
        f"<h2>{spec['study']['name']}</h2>"
        f"<p>Overall: <strong>{summary['overall_status']}</strong></p>"
        f"<p>ICC: {metrics['variance_components']['icc']}</p>"
        "<p>Locked model applied without retraining. "
        "Scientist decision required.</p></body></html>\n"
    )
    _pdf(
        root / "validation_report.pdf",
        [
            "TranscriptForge Validation Study",
            spec["study"]["name"],
            f"Overall: {summary['overall_status']}",
            "Locked model applied without retraining.",
            "Scientist decision required.",
        ],
    )


def _pdf(path: Path, lines: list[str]) -> None:
    def escape(value: str) -> str:
        return (
            value.encode("ascii", "replace")
            .decode()
            .replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )

    commands = ["BT", "/F1 12 Tf", "54 750 Td", "16 TL"]
    for index, line in enumerate(lines):
        if index:
            commands.append("T*")
        commands.append(f"({escape(line[:110])}) Tj")
    commands.append("ET")
    stream = ("\n".join(commands) + "\n").encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(document))
        document.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(document)


def _manifest(root: Path, spec: dict[str, Any], overall: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "bundle_type": "validation_bundle",
        "study_id": spec["study"]["study_id"],
        "study_type": spec["study"]["type"],
        "revision": spec["study"]["revision"],
        "overall_status": overall,
        "locked_model_id": spec["model"]["model_id"],
        "model_retrained": False,
        "files": [
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha(path),
            }
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        ],
        "scientist_decision_required": True,
        "warnings": ["Research use only."],
    }


def _archive(root: Path, target: Path) -> None:
    raw = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for path in sorted(root.rglob("*")):
            if path.is_file():
                info = tarfile.TarInfo(f"validation_bundle/{path.relative_to(root).as_posix()}")
                data = path.read_bytes()
                info.size = len(data)
                info.mtime = 0
                info.mode = 0o444
                archive.addfile(info, io.BytesIO(data))
    target.write_bytes(raw.getvalue())


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("measurement_id\n", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _boolean(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
