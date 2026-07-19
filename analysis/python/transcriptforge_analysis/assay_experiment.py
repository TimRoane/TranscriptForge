"""Deterministic pre-lock input/degradation Development Experiment."""

import csv
import gzip
import hashlib
import html
import json
import math
import platform
import shutil
from dataclasses import asdict, dataclass
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from transcriptforge_analysis.matrix_validation import write_json_atomic
from transcriptforge_analysis.pca import load_bundle_assay

SUPPORTED_EXPERIMENT = "INPUT_DEGRADATION_EXPLORATION"
PAIRED_CONDITION_EXPERIMENT = "PAIRED_CONDITION_COMPARISON"
REQUIRED_ASSIGNMENT_COLUMNS = {
    "measurement_id",
    "biological_sample_id",
    "prepared_dataset_id",
    "include",
    "input_ng",
    "dv200",
    "sequencing_run",
}


@dataclass(frozen=True, slots=True)
class DesignFinding:
    severity: Literal["ERROR", "WARNING", "INFO"]
    code: str
    message: str
    facts: dict[str, Any]
    recommendation: str


@dataclass(frozen=True, slots=True)
class DesignValidation:
    schema_version: str
    valid: bool
    retrospective_mapping: bool
    measurement_count: int
    biological_sample_count: int
    included_measurement_count: int
    reference_level: float
    input_levels: list[float]
    findings: list[DesignFinding]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = [asdict(item) for item in self.findings if item.severity == "ERROR"]
        payload["warnings"] = [asdict(item) for item in self.findings if item.severity == "WARNING"]
        payload["informational"] = [
            asdict(item) for item in self.findings if item.severity == "INFO"
        ]
        return payload


@dataclass(frozen=True, slots=True)
class PairedConditionDesignValidation:
    schema_version: str
    valid: bool
    retrospective_mapping: bool
    measurement_count: int
    biological_sample_count: int
    included_measurement_count: int
    reference_condition: str
    comparator_condition: str
    conditions: list[str]
    complete_pair_count: int
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


def validate_paired_condition_design(
    spec: dict[str, Any], assignments: list[dict[str, str]]
) -> PairedConditionDesignValidation:
    """Validate exact biological pairing and condition/factor identifiability."""
    experiment = spec.get("experiment", {})
    if experiment.get("type") != PAIRED_CONDITION_EXPERIMENT:
        raise ValueError(f"Expected experiment type {PAIRED_CONDITION_EXPERIMENT}.")
    plan = spec.get("analysis_plan", {})
    reference = str(plan.get("reference_condition", "")).strip()
    comparator = str(plan.get("comparator_condition", "")).strip()
    findings: list[DesignFinding] = []
    measurement_ids = [row.get("measurement_id", "") for row in assignments]
    duplicates = sorted({value for value in measurement_ids if measurement_ids.count(value) > 1})
    if duplicates:
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.DUPLICATE_MEASUREMENT",
                "Each measurement_id must be unique.",
                {"duplicate_measurement_ids": duplicates},
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
                    "The include column must contain true or false.",
                    {"measurement_id": row.get("measurement_id", "")},
                    "Correct the include value explicitly.",
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
                    "Record the exclusion reason without deleting the assignment.",
                )
            )
    if not reference or not comparator or reference == comparator:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.CONDITION_CONTRAST_INVALID",
                "Reference and comparator conditions must be distinct and non-empty.",
                {"reference_condition": reference, "comparator_condition": comparator},
                "Select two observed conditions and declare their direction.",
            )
        )
    missing_required = sorted(
        row.get("measurement_id", "")
        for row in included
        if not row.get("biological_sample_id", "")
        or not row.get("condition", "")
        or not row.get("run", "")
    )
    if missing_required:
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.PAIRED_METADATA_REQUIRED",
                "Included measurements require biological sample, condition, and run metadata.",
                {"measurement_ids": missing_required},
                "Map the required fields from explicit sample metadata.",
            )
        )
    conditions = sorted({row.get("condition", "") for row in included if row.get("condition")})
    for declared, role in ((reference, "reference"), (comparator, "comparator")):
        if declared and declared not in conditions:
            findings.append(
                DesignFinding(
                    "ERROR",
                    f"DESIGN.{role.upper()}_CONDITION_MISSING",
                    f"The declared {role} condition is absent.",
                    {"declared_condition": declared, "observed_conditions": conditions},
                    f"Add {role} measurements or select an observed condition.",
                )
            )
    by_sample: dict[str, dict[str, int]] = {}
    for row in included:
        sample = row.get("biological_sample_id", "")
        condition = row.get("condition", "")
        if sample and condition:
            sample_conditions = by_sample.setdefault(sample, {})
            sample_conditions[condition] = sample_conditions.get(condition, 0) + 1
    incomplete = sorted(
        sample
        for sample, counts in by_sample.items()
        if counts.get(reference, 0) != 1 or counts.get(comparator, 0) != 1
    )
    if incomplete:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.PAIRED_CONDITIONS_INCOMPLETE",
                "Each biological sample must have exactly one included reference and comparator measurement.",
                {"biological_sample_ids": incomplete},
                "Complete the pairs, exclude both incomplete measurements with rationale, or use an unpaired design.",
            )
        )
    complete_pairs = sum(
        counts.get(reference, 0) == 1 and counts.get(comparator, 0) == 1
        for counts in by_sample.values()
    )
    if complete_pairs < 3:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.INSUFFICIENT_COMPLETE_PAIRS",
                "At least three complete biological pairs are required for interval estimation.",
                {"complete_pair_count": complete_pairs},
                "Add complete pairs before interpreting paired uncertainty.",
            )
        )
    for factor in ("run", "operator", "reagent_lot"):
        condition_levels: dict[str, set[str]] = {}
        factor_conditions: dict[str, set[str]] = {}
        for row in included:
            condition = row.get("condition", "")
            level = row.get(factor, "")
            if condition and level:
                condition_levels.setdefault(condition, set()).add(level)
                factor_conditions.setdefault(level, set()).add(condition)
        confounded = (
            len(condition_levels) > 1
            and all(len(levels) == 1 for levels in condition_levels.values())
            and all(len(values) == 1 for values in factor_conditions.values())
        )
        if confounded:
            findings.append(
                DesignFinding(
                    "ERROR",
                    f"DESIGN.CONDITION_{factor.upper()}_CONFOUNDED",
                    f"Condition is perfectly aligned with {factor}.",
                    {"condition_levels": {key: sorted(value) for key, value in condition_levels.items()}},
                    f"Distribute both conditions across {factor} levels before comparing them.",
                )
            )
    if experiment.get("mode") == "ANALYZE_EXISTING":
        findings.append(
            DesignFinding(
                "WARNING",
                "DESIGN.RETROSPECTIVE_MAPPING",
                "Assignments were mapped after measurements existed.",
                {"mode": "ANALYZE_EXISTING"},
                "Report that randomization and blocking cannot be repaired retrospectively.",
            )
        )
    return PairedConditionDesignValidation(
        schema_version="1.0.0",
        valid=not any(item.severity == "ERROR" for item in findings),
        retrospective_mapping=experiment.get("mode") == "ANALYZE_EXISTING",
        measurement_count=len(assignments),
        biological_sample_count=len(by_sample),
        included_measurement_count=len(included),
        reference_condition=reference,
        comparator_condition=comparator,
        conditions=conditions,
        complete_pair_count=complete_pairs,
        findings=findings,
    )


def read_assignments(path: Path) -> list[dict[str, str]]:
    """Read an explicit assignment table without inferring values from identifiers."""
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_ASSIGNMENT_COLUMNS - columns)
        if missing:
            raise ValueError("Assignment table is missing columns: " + ", ".join(missing))
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def read_paired_condition_assignments(path: Path) -> list[dict[str, str]]:
    """Read the paired-condition assignment table without guessing condition metadata."""
    required = {
        "measurement_id",
        "biological_sample_id",
        "prepared_dataset_id",
        "include",
        "condition",
        "run",
    }
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        columns = set(reader.fieldnames or [])
        missing = sorted(required - columns)
        if missing:
            raise ValueError("Assignment table is missing columns: " + ", ".join(missing))
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def validate_input_degradation_design(
    spec: dict[str, Any], assignments: list[dict[str, str]]
) -> DesignValidation:
    """Perform blocking and warning checks before any expression computation."""
    experiment = spec.get("experiment", {})
    if experiment.get("type") != SUPPORTED_EXPERIMENT:
        raise ValueError(
            f"This vertical slice supports only {SUPPORTED_EXPERIMENT}; "
            "simplify or select a supported template."
        )
    reference_level = float(spec.get("analysis_plan", {}).get("reference_level"))
    findings: list[DesignFinding] = []
    measurement_ids = [row["measurement_id"] for row in assignments]
    duplicates = sorted({value for value in measurement_ids if measurement_ids.count(value) > 1})
    if duplicates:
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.DUPLICATE_MEASUREMENT",
                "Each measurement_id must be unique.",
                {"duplicate_measurement_ids": duplicates},
                "Remove duplicate rows or assign unique measurement identifiers.",
            )
        )
    included = [row for row in assignments if _parse_include(row["include"])]
    if not included:
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.NO_INCLUDED_MEASUREMENTS",
                "No measurements are included in the experiment.",
                {"included_measurement_count": 0},
                "Include at least one explicitly assigned measurement.",
            )
        )
    excluded_without_reason = sorted(
        row["measurement_id"]
        for row in assignments
        if not _parse_include(row["include"]) and not row.get("exclusion_reason", "")
    )
    if excluded_without_reason:
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.EXCLUSION_REASON_REQUIRED",
                "Every excluded measurement requires a reason.",
                {"measurement_ids": excluded_without_reason},
                "Record an exclusion reason without deleting the original row.",
            )
        )

    numeric_rows: list[tuple[dict[str, str], float, float]] = []
    invalid_numeric: list[str] = []
    for row in included:
        try:
            input_ng = float(row["input_ng"])
            dv200 = float(row["dv200"])
            if not math.isfinite(input_ng) or input_ng <= 0 or not math.isfinite(dv200):
                raise ValueError
            numeric_rows.append((row, input_ng, dv200))
        except ValueError:
            invalid_numeric.append(row["measurement_id"])
    if invalid_numeric:
        findings.append(
            DesignFinding(
                "ERROR",
                "ASSIGNMENT.INVALID_INPUT_OR_DV200",
                "Included measurements require finite positive input_ng and finite DV200.",
                {"measurement_ids": sorted(invalid_numeric)},
                "Correct the declared numeric metadata; values are never inferred from filenames.",
            )
        )

    levels = sorted({input_ng for _, input_ng, _ in numeric_rows}, reverse=True)
    if reference_level not in levels:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.REFERENCE_LEVEL_MISSING",
                "The declared reference input level is not present.",
                {"reference_level": reference_level, "observed_levels": levels},
                "Add the reference measurements or select an observed reference with rationale.",
            )
        )
    if len(levels) < 3:
        findings.append(
            DesignFinding(
                "WARNING",
                "DESIGN.ORDERED_LEVELS_LIMITED",
                "Fewer than three ordered input levels limit trend interpretation.",
                {"observed_levels": levels},
                "Add another ordered level or limit conclusions to the tested pair.",
            )
        )

    by_sample: dict[str, set[float]] = {}
    for row, input_ng, _ in numeric_rows:
        by_sample.setdefault(row["biological_sample_id"], set()).add(input_ng)
    missing_reference = sorted(
        sample
        for sample, sample_levels in by_sample.items()
        if reference_level not in sample_levels
    )
    if missing_reference:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.PAIRED_REFERENCE_MISSING",
                "Some biological samples lack a paired reference measurement.",
                {"biological_sample_ids": missing_reference},
                "Add paired reference measurements or redesign as an explicitly unpaired experiment.",
            )
        )
    incomplete = sorted(
        sample for sample, sample_levels in by_sample.items() if len(sample_levels) < 2
    )
    if incomplete:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.PAIRED_CHALLENGE_MISSING",
                "Some biological samples have no lower-input comparison.",
                {"biological_sample_ids": incomplete},
                "Add a challenge measurement or exclude the incomplete pair with rationale.",
            )
        )

    level_runs: dict[float, set[str]] = {}
    run_levels: dict[str, set[float]] = {}
    for row, input_ng, _ in numeric_rows:
        run = row["sequencing_run"]
        level_runs.setdefault(input_ng, set()).add(run)
        run_levels.setdefault(run, set()).add(input_ng)
    perfect_confounding = (
        len(level_runs) > 1
        and all(len(runs) == 1 for runs in level_runs.values())
        and all(len(run_input_levels) == 1 for run_input_levels in run_levels.values())
    )
    if perfect_confounding:
        findings.append(
            DesignFinding(
                "ERROR",
                "DESIGN.INPUT_RUN_CONFOUNDED",
                "RNA input level is perfectly aligned with sequencing run.",
                {
                    "input_level_runs": {
                        str(level): sorted(runs) for level, runs in level_runs.items()
                    }
                },
                "Rebalance input levels across runs before interpreting an input effect.",
            )
        )
    elif any(len(runs) == 1 for runs in level_runs.values()) and len(run_levels) > 1:
        findings.append(
            DesignFinding(
                "WARNING",
                "DESIGN.INPUT_RUN_IMBALANCE",
                "At least one input level appears in only one sequencing run.",
                {
                    "input_level_runs": {
                        str(level): sorted(runs) for level, runs in level_runs.items()
                    }
                },
                "Interpret that level cautiously and consider a balanced confirmation experiment.",
            )
        )

    if experiment.get("mode") == "ANALYZE_EXISTING":
        findings.append(
            DesignFinding(
                "WARNING",
                "DESIGN.RETROSPECTIVE_MAPPING",
                "Assignments were mapped after measurements existed.",
                {"mode": "ANALYZE_EXISTING"},
                "Report that randomization and blocking cannot be repaired retrospectively.",
            )
        )
    return DesignValidation(
        schema_version="1.0.0",
        valid=not any(item.severity == "ERROR" for item in findings),
        retrospective_mapping=experiment.get("mode") == "ANALYZE_EXISTING",
        measurement_count=len(assignments),
        biological_sample_count=len(by_sample),
        included_measurement_count=len(included),
        reference_level=reference_level,
        input_levels=levels,
        findings=findings,
    )


def run_paired_condition_experiment(
    spec_path: Path,
    assignments_path: Path,
    bundle_archive: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run a deterministic, paired, multi-endpoint condition comparison."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assignments = read_paired_condition_assignments(assignments_path)
    design = validate_paired_condition_design(spec, assignments)
    if not design.valid:
        codes = ", ".join(item.code for item in design.findings if item.severity == "ERROR")
        raise ValueError(f"Experiment design is blocked: {codes}")
    if output_dir.exists():
        raise FileExistsError(output_dir)
    bundle_dir = output_dir / "development_evidence_bundle"
    for relative in (
        "design",
        "endpoints",
        "results",
        "figures",
        "decision",
        "provenance/nextflow_metadata",
        "report",
    ):
        (bundle_dir / relative).mkdir(parents=True, exist_ok=True)

    assay_name = str(spec.get("analysis_plan", {}).get("assay", "log_expression"))
    expression = load_bundle_assay(bundle_archive, assay_name)
    included = [row for row in assignments if _parse_include(row["include"])]
    unknown = sorted(
        {row["measurement_id"] for row in included} - set(expression.sample_ids)
    )
    if unknown:
        raise ValueError(
            "Included measurement IDs are absent from the Expression Bundle: "
            + ", ".join(unknown)
        )
    index = {sample_id: position for position, sample_id in enumerate(expression.sample_ids)}
    measurement_rows: list[dict[str, Any]] = []
    by_sample: dict[str, dict[str, dict[str, Any]]] = {}
    for row in included:
        values = expression.matrix[:, index[row["measurement_id"]]].astype(float)
        finite = bool(np.all(np.isfinite(values)))
        endpoint: dict[str, Any] = {
            **row,
            "quality_metric": _optional_float(row.get("quality_metric", "")),
            "detected_genes": int(np.count_nonzero(np.isfinite(values) & (values != 0))),
            "mean_expression": float(np.mean(values)) if finite else float("nan"),
            "technical_failure": not finite,
        }
        measurement_rows.append(endpoint)
        endpoint["_profile"] = values
        by_sample.setdefault(row["biological_sample_id"], {})[row["condition"]] = endpoint

    pair_rows: list[dict[str, Any]] = []
    for sample_id in sorted(by_sample):
        reference = by_sample[sample_id][design.reference_condition]
        comparator = by_sample[sample_id][design.comparator_condition]
        correlation = _correlation(comparator["_profile"], reference["_profile"])
        quality = comparator["quality_metric"]
        if quality is None:
            quality = reference["quality_metric"]
        pair_rows.append(
            {
                "biological_sample_id": sample_id,
                "reference_measurement_id": reference["measurement_id"],
                "comparator_measurement_id": comparator["measurement_id"],
                "reference_condition": design.reference_condition,
                "comparator_condition": design.comparator_condition,
                "reference_mean_expression": reference["mean_expression"],
                "comparator_mean_expression": comparator["mean_expression"],
                "paired_mean_expression_difference": comparator["mean_expression"]
                - reference["mean_expression"],
                "paired_mean_expression_average": (
                    comparator["mean_expression"] + reference["mean_expression"]
                )
                / 2,
                "detected_genes_difference": comparator["detected_genes"]
                - reference["detected_genes"],
                "expression_profile_correlation": correlation,
                "profile_discordance": 1.0 - correlation,
                "reference_failure": reference["technical_failure"],
                "comparator_failure": comparator["technical_failure"],
                "call_discordant": reference["technical_failure"]
                != comparator["technical_failure"],
                "quality_metric": quality,
            }
        )
    for row in measurement_rows:
        row.pop("_profile")

    differences = np.asarray(
        [row["paired_mean_expression_difference"] for row in pair_rows], dtype=float
    )
    correlations = np.asarray(
        [row["expression_profile_correlation"] for row in pair_rows], dtype=float
    )
    difference_ci = _mean_confidence_interval(differences)
    interaction = _quality_interaction(pair_rows)
    reference_failures = sum(bool(row["reference_failure"]) for row in pair_rows)
    comparator_failures = sum(bool(row["comparator_failure"]) for row in pair_rows)
    condition_results = [
        {
            "reference_condition": design.reference_condition,
            "comparator_condition": design.comparator_condition,
            "pair_count": len(pair_rows),
            "mean_paired_difference": float(np.mean(differences)),
            "paired_difference_confidence_interval_95": difference_ci,
            "median_profile_correlation": float(np.median(correlations)),
            "mean_profile_correlation": float(np.mean(correlations)),
            "mean_profile_discordance": float(np.mean(1.0 - correlations)),
            "reference_failure_rate": reference_failures / len(pair_rows),
            "comparator_failure_rate": comparator_failures / len(pair_rows),
            "failure_rate_difference": (comparator_failures - reference_failures)
            / len(pair_rows),
            "discordant_pair_count": sum(bool(row["call_discordant"]) for row in pair_rows),
            "condition_by_quality_interaction": interaction,
        }
    ]
    primary_results = {
        "schema_version": "1.0.0",
        "experiment_id": spec["experiment"]["experiment_id"],
        "experiment_type": PAIRED_CONDITION_EXPERIMENT,
        "criteria_mode": "exploratory",
        "declared_primary_endpoints": spec["endpoints"]["primary"],
        "declared_secondary_endpoints": spec["endpoints"]["secondary"],
        "condition_results": condition_results,
        "interpretation_boundary": (
            "Exploratory paired evidence across all declared endpoints; no condition is ranked "
            "from a single metric and no acceptance claim is made."
        ),
    }
    comparison = condition_results[0]
    finding = (
        f"Across {len(pair_rows)} complete pairs, {design.comparator_condition} minus "
        f"{design.reference_condition} had a mean expression difference of "
        f"{comparison['mean_paired_difference']:.3f} and median profile correlation "
        f"{comparison['median_profile_correlation']:.3f}."
    )
    decision_summary = {
        "schema_version": "1.0.0",
        "question": spec["question"]["plain_language"],
        "finding": finding,
        "evidence": [
            {
                "type": "paired_multi_endpoint_results",
                "path": "results/primary_results.json",
            },
            {"type": "paired_measurements", "path": "results/paired_differences.tsv"},
            {"type": "bland_altman", "path": "figures/bland_altman.svg"},
        ],
        "limitations": [
            "This is a pre-lock exploratory comparison and has no prespecified acceptance criterion.",
            "A method or condition must not be ranked from one metric alone.",
            "Bland-Altman limits are descriptive normal-approximation limits for the tested pairs.",
            *[item.message for item in design.findings if item.severity == "WARNING"],
        ],
        "criteria_mode": "exploratory",
        "condition_results": condition_results,
        "recommended_next_action_ids": ["PAIRED_CONDITION.SCIENTIST_REVIEW"],
        "scientist_decision_required": True,
    }
    recommendations = {
        "schema_version": "1.0.0",
        "recommendations": [
            {
                "rule_id": "PAIRED_CONDITION.SCIENTIST_REVIEW",
                "title": "Review the paired multi-endpoint evidence",
                "what_to_do": "Review bias, uncertainty, failures, profile concordance, discordant pairs, and quality interaction together.",
                "why": "No single endpoint is sufficient to identify a preferred development condition.",
                "evidence": [{"path": "results/primary_results.json"}],
                "what_it_resolves": "Whether either condition merits a prospectively defined confirmation experiment.",
                "required_inputs": ["scientist interpretation", "context-specific priorities"],
                "expected_output": "An accepted, modified, rejected, or deferred scientist decision.",
                "known_limitations": ["Acceptance never launches a follow-up automatically."],
                "priority": 70,
                "requirement_level": "RECOMMENDED",
                "alternative_actions": ["Collect more complete biological pairs."],
                "one_click_action_template": {
                    "experiment_type": PAIRED_CONDITION_EXPERIMENT,
                    "mode": "PLAN_FIRST",
                    "launch_automatically": False,
                },
                "scientist_decision_required": True,
            }
        ],
    }

    shutil.copyfile(spec_path, bundle_dir / "experiment_spec.json")
    (bundle_dir / "experiment_spec.yaml").write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_json_atomic(bundle_dir / "question.json", spec["question"])
    shutil.copyfile(assignments_path, bundle_dir / "design/experiment_assignments.tsv")
    write_json_atomic(bundle_dir / "design/design_validation.json", design.to_dict())
    _write_paired_factor_balance(bundle_dir / "design/factor_balance.tsv", included)
    _write_paired_confounding(bundle_dir / "design/confounding_matrix.tsv", included)
    _write_endpoint_table(bundle_dir / "endpoints/endpoint_table.tsv.gz", measurement_rows)
    _write_endpoint_parquet(bundle_dir / "endpoints/endpoint_table.parquet", measurement_rows)
    _write_excluded(bundle_dir / "endpoints/excluded_measurements.tsv", assignments)
    _write_plain_tsv(bundle_dir / "results/paired_differences.tsv", pair_rows)
    write_json_atomic(bundle_dir / "results/primary_results.json", primary_results)
    write_json_atomic(
        bundle_dir / "results/secondary_results.json",
        {"schema_version": "1.0.0", "condition_by_quality_interaction": interaction},
    )
    write_json_atomic(
        bundle_dir / "results/model_summaries.json",
        {
            "schema_version": "1.0.0",
            "models": [interaction] if interaction["status"] == "ESTIMATED" else [],
            "note": "Only the declared paired comparison and optional quality interaction were estimated; no predictive model was trained.",
        },
    )
    write_json_atomic(
        bundle_dir / "results/sensitivity_results.json",
        {"schema_version": "1.0.0", "analyses": []},
    )
    write_json_atomic(bundle_dir / "decision/decision_summary.json", decision_summary)
    (bundle_dir / "decision/decision_summary.md").write_text(
        _decision_markdown(decision_summary), encoding="utf-8"
    )
    write_json_atomic(bundle_dir / "decision/recommendations.json", recommendations)
    write_json_atomic(
        bundle_dir / "decision/unresolved_questions.json",
        {
            "schema_version": "1.0.0",
            "questions": ["Do the combined endpoints justify a prospectively defined confirmation?"],
        },
    )
    _write_bland_altman(bundle_dir / "figures/bland_altman.svg", pair_rows, design)
    _write_pair_correlation(bundle_dir / "figures/profile_correlation_by_pair.svg", pair_rows)
    _write_provenance(bundle_dir, spec_path, assignments_path, bundle_archive)
    _write_paired_report(bundle_dir / "report/development_report.html", spec, decision_summary, design)
    _write_report_pdf(bundle_dir / "report/development_report.pdf", spec, decision_summary)
    (bundle_dir / "provenance/nextflow_metadata/README.txt").write_text(
        "Nextflow trace, report, timeline, DAG, stdout, and stderr are launcher-owned artifacts indexed beside this evidence bundle.\n",
        encoding="utf-8",
    )
    manifest = _build_manifest(bundle_dir, spec, decision_summary)
    write_json_atomic(bundle_dir / "manifest.json", manifest)
    shutil.make_archive(
        str(output_dir / "development_evidence_bundle"),
        "gztar",
        root_dir=output_dir,
        base_dir="development_evidence_bundle",
    )
    return manifest


def run_input_degradation_experiment(
    spec_path: Path,
    assignments_path: Path,
    bundle_archive: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Execute one frozen input/degradation exploration and build its evidence bundle."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assignments = read_assignments(assignments_path)
    design = validate_input_degradation_design(spec, assignments)
    if not design.valid:
        codes = ", ".join(item.code for item in design.findings if item.severity == "ERROR")
        raise ValueError(f"Experiment design is blocked: {codes}")
    if output_dir.exists():
        raise FileExistsError(output_dir)
    bundle_dir = output_dir / "development_evidence_bundle"
    for relative in (
        "design",
        "endpoints",
        "results",
        "figures",
        "decision",
        "provenance/nextflow_metadata",
        "report",
    ):
        (bundle_dir / relative).mkdir(parents=True, exist_ok=True)

    assay_name = str(spec.get("analysis_plan", {}).get("assay", "log_expression"))
    expression = load_bundle_assay(bundle_archive, assay_name)
    included = [row for row in assignments if _parse_include(row["include"])]
    assigned_ids = [row["measurement_id"] for row in included]
    unknown = sorted(set(assigned_ids) - set(expression.sample_ids))
    if unknown:
        raise ValueError(
            "Included measurement IDs are absent from the Expression Bundle: " + ", ".join(unknown)
        )
    index = {sample_id: position for position, sample_id in enumerate(expression.sample_ids)}
    reference_level = design.reference_level
    reference_by_sample = {
        row["biological_sample_id"]: row["measurement_id"]
        for row in included
        if float(row["input_ng"]) == reference_level
    }
    endpoint_rows: list[dict[str, Any]] = []
    for row in included:
        measurement_id = row["measurement_id"]
        reference_id = reference_by_sample[row["biological_sample_id"]]
        values = expression.matrix[:, index[measurement_id]].astype(float)
        reference = expression.matrix[:, index[reference_id]].astype(float)
        correlation = _correlation(values, reference)
        endpoint_rows.append(
            {
                **row,
                "input_ng": float(row["input_ng"]),
                "dv200": float(row["dv200"]),
                "reference_measurement_id": reference_id,
                "expression_profile_correlation_to_reference": correlation,
                "detected_genes": int(np.count_nonzero(np.isfinite(values) & (values != 0))),
                "mean_expression": float(np.mean(values)),
            }
        )
    level_results = _summarize_levels(endpoint_rows, reference_level)
    primary_results = {
        "schema_version": "1.0.0",
        "experiment_id": spec["experiment"]["experiment_id"],
        "experiment_type": SUPPORTED_EXPERIMENT,
        "criteria_mode": "exploratory",
        "reference_level": reference_level,
        "condition_results": level_results,
        "interpretation_boundary": (
            "Descriptive pre-lock exploration only; this does not establish a clinical LoD "
            "or final minimum input."
        ),
    }
    lowest_candidate = _lowest_candidate_level(level_results, reference_level)
    finding = (
        f"Expression profiles remained descriptively correlated with their paired reference "
        f"through {lowest_candidate:g} ng under the tested conditions."
        if lowest_candidate is not None
        else "No lower tested input level met the descriptive profile-stability indicator."
    )
    decision_summary = {
        "schema_version": "1.0.0",
        "question": spec["question"]["plain_language"],
        "finding": finding,
        "evidence": [
            {
                "type": "primary_results",
                "path": "results/primary_results.json",
                "condition_results": level_results,
            }
        ],
        "limitations": [
            "The experiment is exploratory and uses no prespecified pass/fail criterion.",
            "This pre-lock exploration does not establish a clinical LoD or final minimum input.",
            "The profile-stability indicator (correlation >= 0.95) is descriptive, not an acceptance threshold.",
            *[item.message for item in design.findings if item.severity == "WARNING"],
        ],
        "criteria_mode": "exploratory",
        "condition_results": level_results,
        "recommended_next_action_ids": ["INPUT_DEGRADATION.BALANCED_CONFIRMATION"],
        "scientist_decision_required": True,
    }
    recommendations = {
        "schema_version": "1.0.0",
        "recommendations": [
            {
                "rule_id": "INPUT_DEGRADATION.BALANCED_CONFIRMATION",
                "title": "Review a balanced confirmation experiment",
                "what_to_do": "Create a new draft experiment around the candidate consecutive input levels.",
                "why": "Exploratory profile stability should be confirmed under balanced run and operator assignments.",
                "evidence": [{"path": "results/primary_results.json"}],
                "what_it_resolves": "Whether the descriptive input behavior persists in a prospectively balanced design.",
                "required_inputs": [
                    "scientist-selected candidate levels",
                    "balanced assignment plan",
                ],
                "expected_output": "A new immutable ExperimentSpec revision after scientist review.",
                "known_limitations": ["Acceptance never launches the follow-up automatically."],
                "priority": 70,
                "requirement_level": "RECOMMENDED",
                "alternative_actions": ["Collect additional metadata before confirmation."],
                "one_click_action_template": {
                    "experiment_type": SUPPORTED_EXPERIMENT,
                    "mode": "PLAN_FIRST",
                    "launch_automatically": False,
                },
                "scientist_decision_required": True,
            }
        ],
    }

    shutil.copyfile(spec_path, bundle_dir / "experiment_spec.json")
    # JSON is a strict subset of YAML. Keeping the exact canonical JSON serialization in
    # the required YAML-named artifact avoids introducing a second, lossy representation.
    (bundle_dir / "experiment_spec.yaml").write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_json_atomic(bundle_dir / "question.json", spec["question"])
    shutil.copyfile(assignments_path, bundle_dir / "design/experiment_assignments.tsv")
    write_json_atomic(bundle_dir / "design/design_validation.json", design.to_dict())
    _write_factor_balance(bundle_dir / "design/factor_balance.tsv", endpoint_rows)
    _write_confounding(bundle_dir / "design/confounding_matrix.tsv", endpoint_rows)
    _write_endpoint_table(bundle_dir / "endpoints/endpoint_table.tsv.gz", endpoint_rows)
    _write_endpoint_parquet(bundle_dir / "endpoints/endpoint_table.parquet", endpoint_rows)
    _write_excluded(bundle_dir / "endpoints/excluded_measurements.tsv", assignments)
    write_json_atomic(bundle_dir / "results/primary_results.json", primary_results)
    write_json_atomic(
        bundle_dir / "results/secondary_results.json",
        {"schema_version": "1.0.0", "level_results": level_results},
    )
    write_json_atomic(
        bundle_dir / "results/model_summaries.json",
        {"schema_version": "1.0.0", "models": [], "note": "No model was trained or retrained."},
    )
    write_json_atomic(
        bundle_dir / "results/sensitivity_results.json",
        {"schema_version": "1.0.0", "analyses": []},
    )
    write_json_atomic(bundle_dir / "decision/decision_summary.json", decision_summary)
    (bundle_dir / "decision/decision_summary.md").write_text(
        _decision_markdown(decision_summary), encoding="utf-8"
    )
    write_json_atomic(bundle_dir / "decision/recommendations.json", recommendations)
    write_json_atomic(
        bundle_dir / "decision/unresolved_questions.json",
        {
            "schema_version": "1.0.0",
            "questions": [
                "Does the descriptive stability persist in a balanced confirmation experiment?"
            ],
        },
    )
    _write_profile_figure(bundle_dir / "figures/profile_stability_by_input.svg", level_results)
    _write_provenance(bundle_dir, spec_path, assignments_path, bundle_archive)
    _write_report(bundle_dir / "report/development_report.html", spec, decision_summary, design)
    _write_report_pdf(bundle_dir / "report/development_report.pdf", spec, decision_summary)
    (bundle_dir / "provenance/nextflow_metadata/README.txt").write_text(
        "Nextflow trace, report, timeline, DAG, stdout, and stderr are launcher-owned "
        "artifacts indexed beside this evidence bundle.\n",
        encoding="utf-8",
    )
    manifest = _build_manifest(bundle_dir, spec, decision_summary)
    write_json_atomic(bundle_dir / "manifest.json", manifest)
    shutil.make_archive(
        str(output_dir / "development_evidence_bundle"),
        "gztar",
        root_dir=output_dir,
        base_dir="development_evidence_bundle",
    )
    return manifest


def _parse_include(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"Invalid include value '{value}'; use true or false.")


def _correlation(left: np.ndarray[Any, Any], right: np.ndarray[Any, Any]) -> float:
    if np.array_equal(left, right):
        return 1.0
    if float(np.std(left)) == 0 or float(np.std(right)) == 0:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def _summarize_levels(rows: list[dict[str, Any]], reference_level: float) -> list[dict[str, Any]]:
    results = []
    for level in sorted({float(row["input_ng"]) for row in rows}, reverse=True):
        level_rows = [row for row in rows if float(row["input_ng"]) == level]
        values = np.array(
            [
                float(row["expression_profile_correlation_to_reference"])
                for row in level_rows
            ],
            dtype=float,
        )
        mean = float(np.mean(values))
        standard_error = (
            float(np.std(values, ddof=1) / math.sqrt(len(values))) if len(values) > 1 else 0.0
        )
        results.append(
            {
                "input_ng": level,
                "measurement_count": len(values),
                "mean_profile_correlation": mean,
                "median_profile_correlation": float(np.median(values)),
                "mean_detected_genes": float(
                    np.mean([float(row["detected_genes"]) for row in level_rows])
                ),
                "mean_expression": float(
                    np.mean([float(row["mean_expression"]) for row in level_rows])
                ),
                "confidence_interval_95": {
                    "lower": max(-1.0, mean - 1.96 * standard_error),
                    "upper": min(1.0, mean + 1.96 * standard_error),
                    "method": "normal_approximation_descriptive",
                },
                "paired_reference": level == reference_level,
                "descriptive_stability_indicator": bool(mean >= 0.95),
            }
        )
    return results


def _lowest_candidate_level(results: list[dict[str, Any]], reference_level: float) -> float | None:
    consecutive: list[float] = []
    for item in results:
        level = float(item["input_ng"])
        if level == reference_level:
            continue
        if not item["descriptive_stability_indicator"]:
            break
        consecutive.append(level)
    return min(consecutive) if consecutive else None


def _optional_float(value: str) -> float | None:
    if not value.strip():
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("quality_metric must be finite when supplied.")
    return parsed


def _mean_confidence_interval(values: np.ndarray[Any, Any]) -> dict[str, Any]:
    mean = float(np.mean(values))
    standard_error = (
        float(np.std(values, ddof=1) / math.sqrt(len(values))) if len(values) > 1 else 0.0
    )
    return {
        "lower": mean - 1.96 * standard_error,
        "upper": mean + 1.96 * standard_error,
        "method": "normal_approximation_paired",
    }


def _quality_interaction(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [row for row in rows if row["quality_metric"] is not None]
    if len(complete) < 3 or len({row["quality_metric"] for row in complete}) < 2:
        return {
            "status": "NOT_ESTIMABLE",
            "reason": "At least three pairs spanning two quality values are required.",
        }
    quality = np.asarray([row["quality_metric"] for row in complete], dtype=float)
    difference = np.asarray(
        [row["paired_mean_expression_difference"] for row in complete], dtype=float
    )
    centered = quality - float(np.mean(quality))
    design = np.column_stack((np.ones(len(centered)), centered))
    coefficients = np.linalg.lstsq(design, difference, rcond=None)[0]
    residual = difference - design @ coefficients
    dof = len(difference) - 2
    if dof <= 0 or float(np.sum(centered**2)) == 0:
        return {"status": "NOT_ESTIMABLE", "reason": "Residual degrees of freedom are zero."}
    variance = float(np.sum(residual**2) / dof)
    slope_se = math.sqrt(variance / float(np.sum(centered**2)))
    slope = float(coefficients[1])
    return {
        "status": "ESTIMATED",
        "endpoint": "paired_mean_expression_difference",
        "quality_field": "quality_metric",
        "pair_count": len(complete),
        "slope": slope,
        "confidence_interval_95": {
            "lower": slope - 1.96 * slope_se,
            "upper": slope + 1.96 * slope_se,
            "method": "ols_normal_approximation",
        },
        "interpretation": "Change in paired condition difference per one-unit quality increase.",
    }


def _write_plain_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_paired_factor_balance(path: Path, rows: list[dict[str, str]]) -> None:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["condition"], row["run"])
        counts[key] = counts.get(key, 0) + 1
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(["condition", "run", "measurement_count"])
        for (condition, run), count in sorted(counts.items()):
            writer.writerow([condition, run, count])


def _write_paired_confounding(path: Path, rows: list[dict[str, str]]) -> None:
    conditions = sorted({row["condition"] for row in rows})
    runs = sorted({row["run"] for row in rows})
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(["condition", *runs])
        for condition in conditions:
            writer.writerow(
                [condition, *[sum(row["condition"] == condition and row["run"] == run for row in rows) for run in runs]]
            )


def _write_bland_altman(
    path: Path,
    rows: list[dict[str, Any]],
    design: PairedConditionDesignValidation,
) -> None:
    width, height, margin = 760, 440, 70
    averages = np.asarray([row["paired_mean_expression_average"] for row in rows], dtype=float)
    differences = np.asarray([row["paired_mean_expression_difference"] for row in rows], dtype=float)
    bias = float(np.mean(differences))
    spread = float(np.std(differences, ddof=1)) if len(rows) > 1 else 0.0
    limits = [bias - 1.96 * spread, bias, bias + 1.96 * spread]
    x_min, x_max = float(np.min(averages)), float(np.max(averages))
    y_min, y_max = min(float(np.min(differences)), limits[0]), max(float(np.max(differences)), limits[2])
    x_pad = max((x_max - x_min) * 0.1, 0.1)
    y_pad = max((y_max - y_min) * 0.1, 0.1)
    x_min, x_max = x_min - x_pad, x_max + x_pad
    y_min, y_max = y_min - y_pad, y_max + y_pad
    def sx(value: float) -> float:
        return margin + (value - x_min) / (x_max - x_min) * (width - 2 * margin)

    def sy(value: float) -> float:
        return height - margin - (value - y_min) / (y_max - y_min) * (
            height - 2 * margin
        )
    circles = "".join(
        f'<circle cx="{sx(float(row["paired_mean_expression_average"])):.1f}" cy="{sy(float(row["paired_mean_expression_difference"])):.1f}" r="6" fill="#7c3aed"><title>{html.escape(str(row["biological_sample_id"]))}</title></circle>'
        for row in rows
    )
    lines = "".join(
        f'<line x1="{margin}" y1="{sy(value):.1f}" x2="{width-margin}" y2="{sy(value):.1f}" stroke="{color}" stroke-dasharray="6 4"/>'
        for value, color in ((limits[0], "#f59e0b"), (limits[1], "#0f766e"), (limits[2], "#f59e0b"))
    )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/><text x="380" y="28" text-anchor="middle" font-size="20" font-weight="700">Paired Bland-Altman comparison</text><line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#334155"/><line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#334155"/>{lines}{circles}<text x="380" y="420" text-anchor="middle" font-size="13">Pair-average expression</text><text x="18" y="220" transform="rotate(-90 18 220)" text-anchor="middle" font-size="13">{html.escape(design.comparator_condition)} - {html.escape(design.reference_condition)}</text></svg>\n',
        encoding="utf-8",
    )


def _write_pair_correlation(path: Path, rows: list[dict[str, Any]]) -> None:
    width, height, margin = 760, 420, 70
    points = []
    for position, row in enumerate(rows):
        x = margin + position * (width - 2 * margin) / max(len(rows) - 1, 1)
        y = height - margin - max(0.0, min(1.0, float(row["expression_profile_correlation"]))) * (height - 2 * margin)
        points.append((x, y, row))
    circles = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#2563eb"><title>{html.escape(str(row["biological_sample_id"]))}: {float(row["expression_profile_correlation"]):.3f}</title></circle>'
        for x, y, row in points
    )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/><text x="380" y="28" text-anchor="middle" font-size="20" font-weight="700">Profile correlation by biological pair</text><line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#334155"/><line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#334155"/>{circles}<text x="18" y="210" transform="rotate(-90 18 210)" text-anchor="middle" font-size="13">Expression-profile correlation</text></svg>\n',
        encoding="utf-8",
    )


def _write_paired_report(
    path: Path,
    spec: dict[str, Any],
    summary: dict[str, Any],
    design: PairedConditionDesignValidation,
) -> None:
    result = summary["condition_results"][0]
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in summary["limitations"])
    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Paired condition comparison</title><style>body{font-family:system-ui;max-width:960px;margin:40px auto;line-height:1.55}.notice{background:#fef3c7;padding:16px;border-radius:8px}img{max-width:100%}</style></head><body>"
        f"<p>DEVELOPMENT EVIDENCE BUNDLE · {PAIRED_CONDITION_EXPERIMENT}</p><h1>{html.escape(spec['experiment']['name'])}</h1><h2>Question</h2><p>{html.escape(summary['question'])}</p><h2>Finding</h2><p>{html.escape(summary['finding'])}</p>"
        "<div class='notice'><strong>Multi-endpoint interpretation required:</strong> do not rank a condition from one metric alone. Scientist decision required.</div>"
        f"<h2>Paired evidence</h2><p>{design.complete_pair_count} complete pairs. Mean paired difference {result['mean_paired_difference']:.3f}; mean profile correlation {result['mean_profile_correlation']:.3f}; failure-rate difference {result['failure_rate_difference']:.3f}.</p>"
        "<img src='../figures/bland_altman.svg' alt='Bland-Altman plot'><img src='../figures/profile_correlation_by_pair.svg' alt='Profile correlations'>"
        f"<h2>Limitations</h2><ul>{limitations}</ul><h2>Next decision</h2><p>Accept, reject, modify, or defer the recommendation. No action was launched automatically.</p></body></html>\n",
        encoding="utf-8",
    )


def _write_endpoint_table(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = list(rows[0])
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        TextIOWrapper(compressed, encoding="utf-8", newline="") as output,
    ):
        writer = csv.DictWriter(
            output, fieldnames=columns, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_endpoint_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    table = pa.Table.from_pylist(rows)
    pq.write_table(
        table,
        path,
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
        data_page_version="2.0",
    )


def _write_excluded(path: Path, assignments: list[dict[str, str]]) -> None:
    excluded = [row for row in assignments if not _parse_include(row["include"])]
    columns = list(assignments[0]) if assignments else sorted(REQUIRED_ASSIGNMENT_COLUMNS)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(excluded)


def _write_factor_balance(path: Path, rows: list[dict[str, Any]]) -> None:
    counts: dict[tuple[float, str], int] = {}
    for row in rows:
        key = (float(row["input_ng"]), str(row["sequencing_run"]))
        counts[key] = counts.get(key, 0) + 1
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(["input_ng", "sequencing_run", "measurement_count"])
        for (level, run), count in sorted(counts.items(), reverse=True):
            writer.writerow([f"{level:g}", run, count])


def _write_confounding(path: Path, rows: list[dict[str, Any]]) -> None:
    levels = sorted({float(row["input_ng"]) for row in rows}, reverse=True)
    runs = sorted({str(row["sequencing_run"]) for row in rows})
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(["input_ng", *runs])
        for level in levels:
            writer.writerow(
                [
                    f"{level:g}",
                    *[
                        sum(
                            float(row["input_ng"]) == level and str(row["sequencing_run"]) == run
                            for row in rows
                        )
                        for run in runs
                    ],
                ]
            )


def _write_profile_figure(path: Path, results: list[dict[str, Any]]) -> None:
    width, height = 760, 420
    margin = 70
    values = list(reversed(results))
    points = []
    for index, item in enumerate(values):
        x = margin + index * (width - 2 * margin) / max(len(values) - 1, 1)
        correlation = float(item["mean_profile_correlation"])
        y = height - margin - max(0.0, min(1.0, correlation)) * (height - 2 * margin)
        points.append((x, y, item))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
    labels = "".join(
        f'<text x="{x:.1f}" y="{height - 35}" text-anchor="middle" font-size="13">{float(item["input_ng"]):g} ng</text>'
        for x, _, item in points
    )
    circles = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#7c3aed"><title>{float(item["mean_profile_correlation"]):.3f}</title></circle>'
        for x, y, item in points
    )
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        '<text x="380" y="28" text-anchor="middle" font-size="20" font-weight="700">Profile stability by RNA input</text>'
        f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#334155"/>'
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#334155"/>'
        f'<line x1="{margin}" y1="{height - margin - 0.95 * (height - 2 * margin):.1f}" x2="{width - margin}" y2="{height - margin - 0.95 * (height - 2 * margin):.1f}" stroke="#f59e0b" stroke-dasharray="5 5"/>'
        f'<polyline points="{polyline}" fill="none" stroke="#7c3aed" stroke-width="3"/>{circles}{labels}'
        '<text x="18" y="210" transform="rotate(-90 18 210)" text-anchor="middle" font-size="13">Mean paired profile correlation</text>'
        '<text x="690" y="78" font-size="11" fill="#92400e">descriptive 0.95 indicator</text></svg>\n',
        encoding="utf-8",
    )


def _write_provenance(
    bundle_dir: Path, spec_path: Path, assignments_path: Path, archive_path: Path
) -> None:
    provenance = bundle_dir / "provenance"
    with (provenance / "input_checksums.tsv").open("w", encoding="utf-8") as output:
        output.write("role\tpath\tsha256\n")
        for role, path in (
            ("experiment_spec", spec_path),
            ("experiment_assignments", assignments_path),
            ("expression_bundle", archive_path),
        ):
            output.write(f"{role}\t{path.name}\t{_sha256(path)}\n")
    (provenance / "software_versions.yml").write_text(
        f"transcriptforge_analysis: 0.1.0\npython: {platform.python_version()}\nnumpy: {np.__version__}\n",
        encoding="utf-8",
    )
    (provenance / "container_digests.tsv").write_text(
        "process\tcontainer_digest\ninput_degradation_exploration\truntime-captured-by-nextflow\n",
        encoding="utf-8",
    )
    write_json_atomic(
        provenance / "parameters.json",
        {"deterministic": True, "random_seed": None, "criteria_mode": "exploratory"},
    )


def _decision_markdown(summary: dict[str, Any]) -> str:
    limitations = "\n".join(f"- {item}" for item in summary["limitations"])
    return (
        f"# Development Experiment decision summary\n\n"
        f"## Question\n\n{summary['question']}\n\n"
        f"## Finding\n\n{summary['finding']}\n\n"
        f"## Limitations\n\n{limitations}\n\n"
        "## Scientist decision\n\nRequired. No next action was launched automatically.\n"
    )


def _write_report(
    path: Path, spec: dict[str, Any], summary: dict[str, Any], design: DesignValidation
) -> None:
    rows = "".join(
        "<tr>"
        f"<td>{item['input_ng']:g}</td><td>{item['measurement_count']}</td>"
        f"<td>{item['mean_profile_correlation']:.3f}</td>"
        f"<td>{'Yes' if item['descriptive_stability_indicator'] else 'No'}</td>"
        "</tr>"
        for item in summary["condition_results"]
    )
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in summary["limitations"])
    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Development Experiment</title>"
        "<style>body{font-family:system-ui;max-width:960px;margin:40px auto;line-height:1.55}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd5e1;padding:8px;text-align:left}"
        ".notice{background:#fef3c7;padding:16px;border-radius:8px}</style></head><body>"
        f"<p>DEVELOPMENT EVIDENCE BUNDLE · {html.escape(spec['experiment']['type'])}</p>"
        f"<h1>{html.escape(spec['experiment']['name'])}</h1>"
        f"<h2>Question</h2><p>{html.escape(summary['question'])}</p>"
        f"<h2>Finding</h2><p>{html.escape(summary['finding'])}</p>"
        "<div class='notice'><strong>Exploratory:</strong> This result does not establish a clinical LoD or final minimum input. Scientist decision required.</div>"
        "<h2>Evidence</h2><img src='../figures/profile_stability_by_input.svg' alt='Profile stability by input'>"
        f"<table><thead><tr><th>Input ng</th><th>N</th><th>Mean correlation</th><th>Descriptive indicator</th></tr></thead><tbody>{rows}</tbody></table>"
        f"<h2>Design</h2><p>{design.included_measurement_count} measurements from {design.biological_sample_count} biological samples.</p>"
        f"<h2>Limitations</h2><ul>{limitations}</ul>"
        "<h2>Next decision</h2><p>Accept, reject, modify, or defer the recommendation. No action was launched automatically.</p>"
        "</body></html>\n",
        encoding="utf-8",
    )


def _write_report_pdf(path: Path, spec: dict[str, Any], summary: dict[str, Any]) -> None:
    """Write a deterministic, dependency-free one-page PDF evidence synopsis."""
    text_lines = [
        "TranscriptForge Development Experiment",
        str(spec["experiment"]["name"]),
        f"Question: {summary['question']}",
        f"Finding: {summary['finding']}",
        "Exploratory development evidence; no clinical LoD or final minimum input is established.",
        "Scientist decision required. No follow-up was launched automatically.",
    ]

    def pdf_escape(value: str) -> str:
        printable = value.encode("ascii", "replace").decode("ascii")
        return printable.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    commands = ["BT", "/F1 12 Tf", "54 750 Td", "16 TL"]
    for index, line in enumerate(text_lines):
        if index:
            commands.append("T*")
        commands.append(f"({pdf_escape(line[:110])}) Tj")
    commands.append("ET")
    stream = ("\n".join(commands) + "\n").encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{index} 0 obj\n".encode())
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(document)


def _build_manifest(
    bundle_dir: Path, spec: dict[str, Any], summary: dict[str, Any]
) -> dict[str, Any]:
    files = []
    for path in sorted(bundle_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append(
                {
                    "path": path.relative_to(bundle_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return {
        "schema_version": "1.0.0",
        "bundle_type": "development_evidence_bundle",
        "experiment_id": spec["experiment"]["experiment_id"],
        "experiment_type": spec["experiment"]["type"],
        "revision": spec["experiment"]["revision"],
        "question": summary["question"],
        "criteria_mode": "exploratory",
        "scientist_decision_required": True,
        "files": files,
        "warnings": [
            "Synthetic or research use only unless the source project explicitly documents otherwise."
        ],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
