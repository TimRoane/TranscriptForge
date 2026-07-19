"""Technical-feasibility pre-lock Development Experiment."""

from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from transcriptforge_analysis.assay_experiment import (
    DesignFinding,
    _build_manifest,
    _decision_markdown,
    _parse_include,
    _write_endpoint_parquet,
    _write_endpoint_table,
    _write_excluded,
    _write_plain_tsv,
    _write_provenance,
    _write_report_pdf,
)
from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.pca import load_bundle_assay

TECHNICAL_FEASIBILITY_EXPERIMENT = "TECHNICAL_FEASIBILITY"


@dataclass(frozen=True, slots=True)
class TechnicalFeasibilityDesignValidation:
    schema_version: str
    valid: bool
    retrospective_mapping: bool
    measurement_count: int
    biological_sample_count: int
    included_measurement_count: int
    run_levels: list[str]
    specimen_groups: list[str]
    findings: list[DesignFinding]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = [asdict(item) for item in self.findings if item.severity == "ERROR"]
        payload["warnings"] = [
            asdict(item) for item in self.findings if item.severity == "WARNING"
        ]
        payload["informational"] = [
            asdict(item) for item in self.findings if item.severity == "INFO"
        ]
        return payload


def _run_value(row: dict[str, str]) -> str:
    return row.get("run", "") or row.get("sequencing_run", "")


def validate_technical_feasibility_design(
    spec: dict[str, Any], assignments: list[dict[str, str]]
) -> TechnicalFeasibilityDesignValidation:
    """Validate explicit feasibility assignments without inventing specimen metadata."""
    if spec.get("experiment", {}).get("type") != TECHNICAL_FEASIBILITY_EXPERIMENT:
        raise ValueError(f"Expected experiment type {TECHNICAL_FEASIBILITY_EXPERIMENT}.")
    findings: list[DesignFinding] = []
    identifiers = [row.get("measurement_id", "") for row in assignments]
    duplicates = sorted(key for key, count in Counter(identifiers).items() if count > 1)
    if duplicates:
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.DUPLICATE_MEASUREMENT",
                "Each measurement_id must be unique.",
                {"measurement_ids": duplicates},
                "Remove duplicate rows or assign unique measurement identifiers.",
            )
        )
    included: list[dict[str, str]] = []
    for row in assignments:
        try:
            include = _parse_include(row.get("include", ""))
        except ValueError:
            include = False
            findings.append(
                DesignFinding(
                    "ERROR",
                    "ASSIGNMENT.INVALID_INCLUDE",
                    "The include field must be explicitly true or false.",
                    {"measurement_id": row.get("measurement_id", "")},
                    "Correct the assignment include value.",
                )
            )
        if include:
            included.append(row)
        elif not row.get("exclusion_reason", ""):
            findings.append(
                DesignFinding(
                    "ERROR",
                    "ASSIGNMENT.EXCLUSION_REASON_REQUIRED",
                    "Every excluded measurement requires a reason.",
                    {"measurement_id": row.get("measurement_id", "")},
                    "Record the exclusion reason without deleting the row.",
                )
            )
    missing = sorted(
        row.get("measurement_id", "")
        for row in included
        if not row.get("biological_sample_id", "") or not _run_value(row)
    )
    if missing:
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.FEASIBILITY_METADATA_REQUIRED",
                "Included measurements require biological-sample and run metadata.",
                {"measurement_ids": missing},
                "Map explicit biological-sample and run fields.",
            )
        )
    samples = sorted(
        {
            row.get("biological_sample_id", "")
            for row in included
            if row.get("biological_sample_id")
        }
    )
    if len(included) < 4 or len(samples) < 2:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.FEASIBILITY_SAMPLE_COUNT",
                "At least four measurements from two biological samples are required.",
                {"measurements": len(included), "biological_samples": len(samples)},
                "Collect or include additional measurements before summarizing feasibility.",
            )
        )
    specimen_groups = sorted(
        {
            row.get("specimen_group", "")
            for row in included
            if row.get("specimen_group")
        }
    )
    if not specimen_groups:
        findings.append(
            DesignFinding(
                "WARNING",
                "DESIGN.SPECIMEN_GROUP_UNAVAILABLE",
                "No specimen-group field is available for stratified feasibility review.",
                {},
                "Interpret only the all-measurement summary or add an explicit specimen group.",
            )
        )
    if not any(
        row.get("input_ng") or row.get("dv200") or row.get("quality_metric")
        for row in included
    ):
        findings.append(
            DesignFinding(
                "WARNING",
                "DESIGN.RNA_QUALITY_METADATA_UNAVAILABLE",
                "RNA quantity/quality metadata are absent.",
                {},
                "Limit interpretation to expression-derived suitability and explicit failures.",
            )
        )
    if spec.get("experiment", {}).get("mode") == "ANALYZE_EXISTING":
        findings.append(
            DesignFinding(
                "WARNING",
                "DESIGN.RETROSPECTIVE_MAPPING",
                "Assignments were mapped after measurements existed.",
                {"mode": "ANALYZE_EXISTING"},
                "Report that randomization and blocking cannot be repaired retrospectively.",
            )
        )
    return TechnicalFeasibilityDesignValidation(
        schema_version="1.0.0",
        valid=not any(item.severity == "ERROR" for item in findings),
        retrospective_mapping=spec.get("experiment", {}).get("mode") == "ANALYZE_EXISTING",
        measurement_count=len(assignments),
        biological_sample_count=len(samples),
        included_measurement_count=len(included),
        run_levels=sorted({_run_value(row) for row in included if _run_value(row)}),
        specimen_groups=specimen_groups,
        findings=findings,
    )


def read_technical_feasibility_assignments(path: Path) -> list[dict[str, str]]:
    """Read the bounded assignment contract without filename inference."""
    required = {
        "measurement_id",
        "biological_sample_id",
        "prepared_dataset_id",
        "include",
    }
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError("Assignment table is missing columns: " + ", ".join(missing))
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def _optional_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    parsed = float(value)
    return parsed if np.isfinite(parsed) else None


def _failure(value: str | None) -> bool:
    return str(value or "false").strip().lower() in {"true", "1", "yes"}


def run_technical_feasibility_experiment(
    spec_path: Path, assignments_path: Path, bundle_archive: Path, output_dir: Path
) -> dict[str, Any]:
    """Summarize technical usability and failure patterns as exploratory evidence."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assignments = read_technical_feasibility_assignments(assignments_path)
    design = validate_technical_feasibility_design(spec, assignments)
    if not design.valid:
        codes = ", ".join(item.code for item in design.findings if item.severity == "ERROR")
        raise ValueError(f"Experiment design is blocked: {codes}")
    if output_dir.exists():
        raise FileExistsError(output_dir)
    root = output_dir / "development_evidence_bundle"
    for relative in (
        "design",
        "endpoints",
        "results",
        "figures",
        "decision",
        "provenance/nextflow_metadata",
        "report",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    expression = load_bundle_assay(bundle_archive, str(spec["analysis_plan"]["assay"]))
    index = {sample_id: position for position, sample_id in enumerate(expression.sample_ids)}
    included = [row for row in assignments if _parse_include(row["include"])]
    unknown = sorted({row["measurement_id"] for row in included} - set(index))
    if unknown:
        raise ValueError(
            "Included measurements are absent from the Expression Bundle: " + ", ".join(unknown)
        )
    endpoints: list[dict[str, Any]] = []
    for row in included:
        values = expression.matrix[:, index[row["measurement_id"]]].astype(float)
        finite = bool(np.all(np.isfinite(values)))
        endpoints.append(
            {
                **row,
                "run": _run_value(row),
                "input_ng": _optional_float(row.get("input_ng")),
                "dv200": _optional_float(row.get("dv200")),
                "quality_metric": _optional_float(row.get("quality_metric")),
                "detected_genes": int(np.count_nonzero(np.isfinite(values) & (values != 0))),
                "mean_expression": float(np.mean(values)) if finite else None,
                "technical_failure": _failure(row.get("technical_failure")) or not finite,
            }
        )
    group_names = sorted({str(row.get("specimen_group") or "all") for row in endpoints})
    condition_results = []
    for group in group_names:
        selected = [row for row in endpoints if str(row.get("specimen_group") or "all") == group]
        condition_results.append(_summary(group, selected))
    all_summary = _summary("all", endpoints)
    factor_review = {}
    for factor in ("specimen_group", "run", "operator"):
        levels = sorted({str(row.get(factor) or "not_recorded") for row in endpoints})
        factor_review[factor] = [
            _summary(
                level,
                [
                    row
                    for row in endpoints
                    if str(row.get(factor) or "not_recorded") == level
                ],
            )
            for level in levels
        ]
    primary = {
        "schema_version": "1.0.0",
        "experiment_id": spec["experiment"]["experiment_id"],
        "experiment_type": TECHNICAL_FEASIBILITY_EXPERIMENT,
        "criteria_mode": "exploratory",
        "overall_summary": all_summary,
        "condition_results": condition_results,
        "failure_association_review": factor_review,
        "interpretation_boundary": (
            "Technical feasibility under the tested research conditions only; no clinical, "
            "regulatory, or final specimen-acceptance claim is established."
        ),
    }
    finding = (
        f"{all_summary['successful_measurements']} of {all_summary['measurement_count']} included "
        f"measurements were technically usable under the tested conditions."
    )
    summary = {
        "schema_version": "1.0.0",
        "question": spec["question"]["plain_language"],
        "finding": finding,
        "evidence": [
            {"type": "technical_feasibility", "path": "results/primary_results.json"},
            {"type": "measurement_endpoints", "path": "endpoints/endpoint_table.parquet"},
        ],
        "limitations": [
            "Synthetic or retrospective feasibility evidence is not evidence about a real assay.",
            "Failure associations are descriptive and may be confounded.",
            "No final specimen requirement or clinical claim is established.",
            *[item.message for item in design.findings if item.severity == "WARNING"],
        ],
        "criteria_mode": "exploratory",
        "condition_results": condition_results,
        "recommended_next_action_ids": ["TECHNICAL_FEASIBILITY.SCIENTIST_REVIEW"],
        "scientist_decision_required": True,
    }
    recommendations = {
        "schema_version": "1.0.0",
        "recommendations": [
            {
                "rule_id": "TECHNICAL_FEASIBILITY.SCIENTIST_REVIEW",
                "title": "Review whether feasibility evidence supports another experiment",
                "what_to_do": (
                    "Review success, RNA quantity/quality, expression suitability, batch, and "
                    "specimen-group patterns together."
                ),
                "why": "A software success proportion cannot choose the development milestone.",
                "evidence": [{"path": "results/primary_results.json"}],
                "what_it_resolves": "Whether to proceed, investigate failures, or collect data.",
                "required_inputs": ["scientist interpretation", "intended research context"],
                "expected_output": "An accepted, modified, rejected, or deferred decision.",
                "known_limitations": ["No action launches automatically."],
                "priority": 75,
                "requirement_level": "RECOMMENDED",
                "alternative_actions": [
                    "Investigate failure-associated technical factors.",
                    "Collect missing specimen or RNA-quality metadata.",
                ],
                "one_click_action_template": {
                    "experiment_type": "INPUT_DEGRADATION_EXPLORATION",
                    "mode": "PLAN_FIRST",
                    "launch_automatically": False,
                },
                "scientist_decision_required": True,
            }
        ],
    }
    shutil.copyfile(spec_path, root / "experiment_spec.json")
    (root / "experiment_spec.yaml").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    write_json_atomic(root / "question.json", spec["question"])
    shutil.copyfile(assignments_path, root / "design/experiment_assignments.tsv")
    write_json_atomic(root / "design/design_validation.json", design.to_dict())
    _write_plain_tsv(
        root / "design/factor_balance.tsv",
        [row for values in factor_review.values() for row in values],
    )
    _write_plain_tsv(
        root / "design/confounding_matrix.tsv",
        [
            {
                "note": (
                    "Descriptive feasibility summaries; no adjusted group-effect model was "
                    "fitted."
                )
            }
        ],
    )
    _write_endpoint_table(root / "endpoints/endpoint_table.tsv.gz", endpoints)
    _write_endpoint_parquet(root / "endpoints/endpoint_table.parquet", endpoints)
    _write_excluded(root / "endpoints/excluded_measurements.tsv", assignments)
    write_json_atomic(root / "results/primary_results.json", primary)
    write_json_atomic(
        root / "results/secondary_results.json",
        {"failure_association_review": factor_review},
    )
    write_json_atomic(
        root / "results/model_summaries.json",
        {"models": [], "note": "No inferential group-effect model was fitted."},
    )
    write_json_atomic(root / "results/sensitivity_results.json", {"analyses": []})
    write_json_atomic(root / "decision/decision_summary.json", summary)
    (root / "decision/decision_summary.md").write_text(_decision_markdown(summary))
    write_json_atomic(root / "decision/recommendations.json", recommendations)
    write_json_atomic(
        root / "decision/unresolved_questions.json", {"questions": summary["limitations"]}
    )
    _write_feasibility_figure(root / "figures/technical_success_by_group.svg", condition_results)
    _write_provenance(root, spec_path, assignments_path, bundle_archive)
    root.joinpath("report/development_report.html").write_text(
        "<!doctype html><html><body><h1>Technical feasibility experiment</h1>"
        f"<p>{finding}</p><p>Research-use evidence; scientist decision required.</p>"
        "</body></html>\n"
    )
    _write_report_pdf(root / "report/development_report.pdf", spec, summary)
    (root / "provenance/nextflow_metadata/README.txt").write_text(
        "Nextflow execution metadata is indexed beside this bundle.\n"
    )
    manifest = _build_manifest(root, spec, summary)
    write_json_atomic(root / "manifest.json", manifest)
    shutil.make_archive(
        str(output_dir / "development_evidence_bundle"),
        "gztar",
        root_dir=output_dir,
        base_dir="development_evidence_bundle",
    )
    return manifest


def _summary(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [not bool(row["technical_failure"]) for row in rows]
    return {
        "group": label,
        "measurement_count": len(rows),
        "successful_measurements": sum(successes),
        "technical_success_rate": float(np.mean(successes)) if rows else None,
        "median_input_ng": _median(rows, "input_ng"),
        "median_dv200": _median(rows, "dv200"),
        "median_quality_metric": _median(rows, "quality_metric"),
        "median_detected_genes": _median(rows, "detected_genes"),
    }


def _median(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return float(np.median(values)) if values else None


def _write_feasibility_figure(path: Path, rows: list[dict[str, Any]]) -> None:
    width, height, margin = 720, 400, 70
    bar_width = max((width - 2 * margin) / max(len(rows), 1) * 0.55, 20)
    bars = []
    for index, row in enumerate(rows):
        rate = float(row["technical_success_rate"] or 0)
        x = margin + (index + 0.5) * (width - 2 * margin) / max(len(rows), 1)
        bar_height = rate * (height - 2 * margin)
        bars.append(
            f'<rect x="{x - bar_width / 2:.1f}" y="{height - margin - bar_height:.1f}" '
            f'width="{bar_width:.1f}" height="{bar_height:.1f}" fill="#6d28d9"/>'
            f'<text x="{x:.1f}" y="{height - margin + 20}" text-anchor="middle">'
            f'{row["group"]}</text>'
        )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="{width / 2}" y="30" text-anchor="middle">Technical success rate</text>'
        + "".join(bars)
        + "</svg>\n"
    )
