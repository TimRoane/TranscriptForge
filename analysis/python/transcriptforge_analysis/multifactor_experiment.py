"""Constrained, deterministic multifactor pre-lock Development Experiment."""

from __future__ import annotations

import json
import math
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
    read_paired_condition_assignments,
)
from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.pca import load_bundle_assay

MULTIFACTOR_EXPERIMENT = "MULTIFACTOR_OPTIMIZATION"
NUMERIC_FACTORS = {"input_ng", "dv200", "sequencing_depth"}


@dataclass(frozen=True, slots=True)
class MultifactorDesignValidation:
    schema_version: str
    valid: bool
    retrospective_mapping: bool
    measurement_count: int
    biological_sample_count: int
    included_measurement_count: int
    factors: list[str]
    interactions: list[str]
    factor_levels: dict[str, list[str]]
    design_matrix_rank: int
    design_matrix_columns: int
    residual_degrees_of_freedom: int
    findings: list[DesignFinding]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = [asdict(item) for item in self.findings if item.severity == "ERROR"]
        payload["warnings"] = [asdict(item) for item in self.findings if item.severity == "WARNING"]
        payload["informational"] = [
            asdict(item) for item in self.findings if item.severity == "INFO"
        ]
        return payload


def validate_multifactor_design(
    spec: dict[str, Any], assignments: list[dict[str, str]]
) -> MultifactorDesignValidation:
    """Reject unbounded, sparse, or rank-deficient factorial requests."""
    if spec.get("experiment", {}).get("type") != MULTIFACTOR_EXPERIMENT:
        raise ValueError(f"Expected experiment type {MULTIFACTOR_EXPERIMENT}.")
    plan = spec.get("analysis_plan", {})
    factors = [str(value) for value in plan.get("factor_names", [])]
    interactions = [str(value) for value in plan.get("interactions", [])]
    findings: list[DesignFinding] = []
    if not 2 <= len(factors) <= 3 or len(factors) != len(set(factors)):
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.MULTIFACTOR_BOUNDS",
                "Select two or three unique primary factors.",
                {"factor_names": factors},
                "Simplify the experiment to at most three primary factors.",
            )
        )
    included = [row for row in assignments if _parse_include(row.get("include", ""))]
    identifiers = [row.get("measurement_id", "") for row in assignments]
    if len(identifiers) != len(set(identifiers)):
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.DUPLICATE_MEASUREMENT",
                "Each measurement_id must be unique.",
                {},
                "Remove duplicate assignment rows.",
            )
        )
    missing = sorted(
        row.get("measurement_id", "")
        for row in included
        if not row.get("biological_sample_id")
        or not row.get("run")
        or any(not row.get(factor, "") for factor in factors)
    )
    if missing:
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.MULTIFACTOR_METADATA_REQUIRED",
                "Included measurements require sample, run, and every declared factor.",
                {"measurement_ids": missing},
                "Complete explicit metadata mapping before analysis.",
            )
        )
    sample_counts = Counter(row.get("biological_sample_id", "") for row in included)
    unrepeated = sorted(key for key, count in sample_counts.items() if key and count < 2)
    if unrepeated:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.REPEATED_SAMPLES_REQUIRED",
                "Every biological sample requires at least two factor combinations.",
                {"biological_sample_ids": unrepeated},
                "Add repeated conditions or simplify to an independent-sample design.",
            )
        )
    factor_levels = {
        factor: sorted({row.get(factor, "") for row in included if row.get(factor, "")})
        for factor in factors
    }
    for factor, levels in factor_levels.items():
        if len(levels) < 2:
            findings.append(
                DesignFinding(
                    "ERROR",
                    "DESIGN.FACTOR_LEVELS_INSUFFICIENT",
                    f"Factor '{factor}' requires at least two observed levels.",
                    {"levels": levels},
                    "Add an observed factor level or remove the factor.",
                )
            )
    matrix, names = _design_matrix(included, factors, interactions, include_blocks=True)
    rank = int(np.linalg.matrix_rank(matrix)) if matrix.size else 0
    residual_df = len(included) - rank
    if matrix.shape[1] and rank < matrix.shape[1]:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.MULTIFACTOR_RANK_DEFICIENT",
                "The requested factors, interactions, sample blocks, and run are not identifiable.",
                {"rank": rank, "columns": len(names)},
                "Remove an interaction, rebalance factors across runs, or collect missing cells.",
            )
        )
    if residual_df < 3 or (matrix.shape[1] and len(included) < 2 * matrix.shape[1]):
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.MULTIFACTOR_TOO_SPARSE",
                "The design is too sparse for the requested model and uncertainty estimates.",
                {
                    "measurements": len(included),
                    "columns": matrix.shape[1],
                    "residual_df": residual_df,
                },
                "Collect replicated cells or simplify factors/interactions.",
            )
        )
    cell_counts = Counter(tuple(row.get(factor, "") for factor in factors) for row in included)
    thin = [list(cell) for cell, count in cell_counts.items() if count < 2]
    if thin:
        findings.append(
            DesignFinding(
                "WARNING",
                "DESIGN.MULTIFACTOR_THIN_CELLS",
                "Some observed factor cells have fewer than two measurements.",
                {"cells": thin},
                "Interpret those cell means cautiously or add replication.",
            )
        )
    return MultifactorDesignValidation(
        schema_version="1.0.0",
        valid=not any(item.severity == "ERROR" for item in findings),
        retrospective_mapping=spec.get("experiment", {}).get("mode") == "ANALYZE_EXISTING",
        measurement_count=len(assignments),
        biological_sample_count=len(sample_counts),
        included_measurement_count=len(included),
        factors=factors,
        interactions=interactions,
        factor_levels=factor_levels,
        design_matrix_rank=rank,
        design_matrix_columns=int(matrix.shape[1]) if matrix.ndim == 2 else 0,
        residual_degrees_of_freedom=residual_df,
        findings=findings,
    )


def _factor_columns(
    rows: list[dict[str, str]], factor: str
) -> list[tuple[str, np.ndarray[Any, Any]]]:
    if factor in NUMERIC_FACTORS:
        values = np.asarray([float(row[factor]) for row in rows], dtype=float)
        return [(factor, values - float(np.mean(values)))]
    categorical_values = [row.get(factor, "") for row in rows]
    levels = sorted(set(categorical_values))
    return [
        (
            f"{factor}[{level}]",
            np.asarray([float(value == level) for value in categorical_values]),
        )
        for level in levels[1:]
    ]


def _design_matrix(
    rows: list[dict[str, str]], factors: list[str], interactions: list[str], *, include_blocks: bool
) -> tuple[np.ndarray[Any, Any], list[str]]:
    columns: list[np.ndarray[Any, Any]] = [np.ones(len(rows))]
    names = ["intercept"]
    terms: dict[str, list[tuple[str, np.ndarray[Any, Any]]]] = {}
    for factor in factors:
        terms[factor] = _factor_columns(rows, factor)
        for name, values in terms[factor]:
            names.append(name)
            columns.append(values)
    for interaction in interactions:
        left, right = interaction.split(":")
        for left_name, left_values in terms[left]:
            for right_name, right_values in terms[right]:
                names.append(f"{left_name}:{right_name}")
                columns.append(left_values * right_values)
    if include_blocks:
        for block in ("biological_sample_id", "run"):
            block_values = [row.get(block, "") for row in rows]
            for level in sorted(set(block_values))[1:]:
                names.append(f"{block}[{level}]")
                columns.append(np.asarray([float(value == level) for value in block_values]))
    return (np.column_stack(columns) if rows else np.empty((0, 0))), names


def run_multifactor_experiment(
    spec_path: Path, assignments_path: Path, bundle_archive: Path, output_dir: Path
) -> dict[str, Any]:
    """Estimate the frozen constrained model and emit a Development Evidence Bundle."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assignments = read_paired_condition_assignments(assignments_path)
    design = validate_multifactor_design(spec, assignments)
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
    index = {value: position for position, value in enumerate(expression.sample_ids)}
    included = [row for row in assignments if _parse_include(row["include"])]
    if {row["measurement_id"] for row in included} - set(index):
        raise ValueError("Included measurements are absent from the Expression Bundle.")
    endpoints: list[dict[str, Any]] = []
    for row in included:
        values = expression.matrix[:, index[row["measurement_id"]]].astype(float)
        endpoints.append(
            {
                **row,
                "mean_expression": float(np.mean(values)),
                "detected_genes": int(np.count_nonzero(np.isfinite(values) & (values != 0))),
            }
        )
    factors = design.factors
    matrix, names = _design_matrix(included, factors, design.interactions, include_blocks=True)
    outcome = np.asarray([row["mean_expression"] for row in endpoints], dtype=float)
    coefficients, _, _, _ = np.linalg.lstsq(matrix, outcome, rcond=None)
    residuals = outcome - matrix @ coefficients
    residual_sd = float(np.sqrt(np.sum(residuals**2) / design.residual_degrees_of_freedom))
    covariance = np.linalg.pinv(matrix.T @ matrix) * residual_sd**2
    estimates = [
        {
            "term": name,
            "estimate": float(value),
            "standard_error": float(math.sqrt(max(covariance[i, i], 0))),
            "confidence_interval_95": {
                "lower": float(value - 1.96 * math.sqrt(max(covariance[i, i], 0))),
                "upper": float(value + 1.96 * math.sqrt(max(covariance[i, i], 0))),
            },
        }
        for i, (name, value) in enumerate(zip(names, coefficients, strict=True))
    ]
    sample_means = [
        float(
            np.mean(
                [
                    row["mean_expression"]
                    for row in endpoints
                    if row["biological_sample_id"] == sample
                ]
            )
        )
        for sample in sorted({str(row["biological_sample_id"]) for row in endpoints})
    ]
    variance = {
        "between_biological_sample": float(np.var(sample_means, ddof=1)),
        "model_residual": float(np.var(residuals, ddof=1)),
        "repeated_sample_method": "biological_sample_fixed_block",
    }
    grouped: dict[tuple[str, ...], list[float]] = {}
    for row in endpoints:
        grouped.setdefault(tuple(str(row[factor]) for factor in factors), []).append(
            float(row["mean_expression"])
        )
    condition_results = [
        {
            **{factor: cell[i] for i, factor in enumerate(factors)},
            "measurement_count": len(values),
            "mean_expression": float(np.mean(values)),
        }
        for cell, values in sorted(grouped.items())
    ]
    response_surface = _response_surface(root / "figures/response_surface.svg", endpoints, factors)
    primary = {
        "schema_version": "1.0.0",
        "experiment_id": spec["experiment"]["experiment_id"],
        "experiment_type": MULTIFACTOR_EXPERIMENT,
        "criteria_mode": "exploratory",
        "fixed_effect_estimates": estimates,
        "variance_decomposition": variance,
        "condition_results": condition_results,
        "response_surface": response_surface,
    }
    finding = (
        f"The constrained model estimated {len(estimates) - 1} declared or blocking terms "
        f"with {design.residual_degrees_of_freedom} residual degrees of freedom."
    )
    summary = {
        "schema_version": "1.0.0",
        "question": spec["question"]["plain_language"],
        "finding": finding,
        "evidence": [{"type": "fixed_effects", "path": "results/primary_results.json"}],
        "limitations": [
            "This is exploratory pre-lock optimization, not a final acceptance study.",
            "Only prespecified factors and interactions were fitted.",
            "Biological samples are fixed blocks; variance components are descriptive.",
        ],
        "criteria_mode": "exploratory",
        "condition_results": condition_results,
        "recommended_next_action_ids": ["MULTIFACTOR.SCIENTIST_REVIEW"],
        "scientist_decision_required": True,
    }
    recommendations = {
        "schema_version": "1.0.0",
        "recommendations": [
            {
                "rule_id": "MULTIFACTOR.SCIENTIST_REVIEW",
                "title": "Review the constrained multifactor evidence",
                "what_to_do": (
                    "Review effect intervals, variance, cell support, and any response surface "
                    "together."
                ),
                "why": (
                    "Optimization remains a scientist decision and no single coefficient "
                    "selects a final assay condition."
                ),
                "evidence": [{"path": "results/primary_results.json"}],
                "what_it_resolves": "Which conditions merit prospective confirmation.",
                "required_inputs": ["scientist interpretation"],
                "expected_output": "A recorded development decision.",
                "known_limitations": ["No follow-up launches automatically."],
                "priority": 70,
                "requirement_level": "RECOMMENDED",
                "alternative_actions": ["Collect more replicated factor cells."],
                "one_click_action_template": {
                    "experiment_type": MULTIFACTOR_EXPERIMENT,
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
    _write_plain_tsv(root / "design/factor_balance.tsv", condition_results)
    _write_plain_tsv(root / "design/confounding_matrix.tsv", [{"term": name} for name in names])
    _write_endpoint_table(root / "endpoints/endpoint_table.tsv.gz", endpoints)
    _write_endpoint_parquet(root / "endpoints/endpoint_table.parquet", endpoints)
    _write_excluded(root / "endpoints/excluded_measurements.tsv", assignments)
    write_json_atomic(root / "results/primary_results.json", primary)
    write_json_atomic(root / "results/secondary_results.json", {"variance_decomposition": variance})
    write_json_atomic(
        root / "results/model_summaries.json",
        {"models": [{"terms": estimates, "residual_sd": residual_sd}]},
    )
    write_json_atomic(root / "results/sensitivity_results.json", {"analyses": []})
    write_json_atomic(root / "decision/decision_summary.json", summary)
    (root / "decision/decision_summary.md").write_text(_decision_markdown(summary))
    write_json_atomic(root / "decision/recommendations.json", recommendations)
    write_json_atomic(
        root / "decision/unresolved_questions.json", {"questions": summary["limitations"]}
    )
    _write_provenance(root, spec_path, assignments_path, bundle_archive)
    root.joinpath("report/development_report.html").write_text(
        "<!doctype html><html><body><h1>Constrained multifactor optimization</h1>"
        f"<p>{finding}</p><p>Scientist decision required.</p></body></html>\n"
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


def _response_surface(path: Path, rows: list[dict[str, Any]], factors: list[str]) -> dict[str, Any]:
    numeric = [factor for factor in factors if factor in NUMERIC_FACTORS]
    if len(numeric) != 2:
        return {
            "status": "NOT_SUPPORTED",
            "reason": "Exactly two numeric primary factors are required.",
        }
    x_name, y_name = numeric
    width, height, margin = 720, 420, 60
    xs = np.asarray([float(row[x_name]) for row in rows])
    ys = np.asarray([float(row[y_name]) for row in rows])
    scores = np.asarray([float(row["mean_expression"]) for row in rows])

    def scale(value: float, low: float, high: float, size: int) -> float:
        return margin + (value - low) / max(high - low, 1e-12) * (size - 2 * margin)

    circles = "".join(
        "<circle "
        f'cx="{scale(x, float(xs.min()), float(xs.max()), width):.1f}" '
        f'cy="{height - scale(y, float(ys.min()), float(ys.max()), height):.1f}" '
        f'r="{4 + 5 * (score - scores.min()) / max(float(np.ptp(scores)), 1e-12):.1f}" '
        'fill="#6d28d9" opacity="0.65"/>'
        for x, y, score in zip(xs, ys, scores, strict=True)
    )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="{width / 2}" y="{height - 10}" text-anchor="middle">{x_name}</text>'
        f'<text x="15" y="{height / 2}">{y_name}</text>{circles}</svg>\n'
    )
    return {"status": "GENERATED", "factors": numeric, "path": "figures/response_surface.svg"}
