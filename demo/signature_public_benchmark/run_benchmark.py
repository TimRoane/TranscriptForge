"""Run the frozen GSE39795 signature-method benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from transcriptforge_analysis.signature_scoring import (
    SignatureScoringConfig,
    run_signature_scoring,
)

ROOT_ENV = os.environ.get("TRANSCRIPTFORGE_ROOT")
ROOT = Path(ROOT_ENV) if ROOT_ENV else Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent
POLICY_PATH = FIXTURE / "benchmark_policy.json"
PYTHON_METHODS = ("mean_expression", "mean_z_score", "weighted_linear", "rank_based")
R_METHODS = ("gsva", "ssgsea")


def run_benchmark(
    bundle: Path, output_dir: Path, *, r_runner: Path | None = None
) -> dict[str, Any]:
    """Score every supported method and apply the prespecified policy."""
    policy = json.loads(POLICY_PATH.read_text())
    policy_sha256 = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
    bundle_sha256 = hashlib.sha256(bundle.read_bytes()).hexdigest()
    expected_bundle = policy["dataset"]["expression_bundle_sha256"]
    if bundle_sha256 != expected_bundle:
        raise ValueError(
            f"Expression Bundle SHA-256 {bundle_sha256} does not match policy {expected_bundle}."
        )
    signature_path = FIXTURE / policy["signature"]["source"]
    signature_sha256 = hashlib.sha256(signature_path.read_bytes()).hexdigest()
    if signature_sha256 != policy["signature"]["sha256"]:
        raise ValueError("Benchmark signature checksum does not match the frozen policy.")
    signature_sets = _read_gmt(signature_path)
    available_features = _bundle_features(bundle)
    mapping_report = _mapping_report(
        signature_sha256, bundle_sha256, signature_sets, available_features
    )
    mapping_bytes = _json_bytes(mapping_report)
    mapping_sha256 = hashlib.sha256(mapping_bytes).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "signature_mapping.json").write_bytes(mapping_bytes)

    method_results = []
    for method in (*PYTHON_METHODS, *R_METHODS):
        method_output = output_dir / method
        request = _request(method, mapping_sha256, mapping_report, policy)
        if method in PYTHON_METHODS:
            config = SignatureScoringConfig.from_json(_write_request(output_dir, method, request))
            summary = run_signature_scoring(bundle, config, method_output)
        else:
            if r_runner is None:
                raise ValueError("GSVA/ssGSEA benchmarking requires --r-runner.")
            request_path = _write_request(output_dir, method, request)
            completed = subprocess.run(
                [
                    "Rscript",
                    str(r_runner),
                    "--request",
                    str(request_path),
                    "--bundle",
                    str(bundle),
                    "--output-dir",
                    str(method_output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode:
                raise RuntimeError(
                    f"{method} benchmark failed: {completed.stderr or completed.stdout}"
                )
            summary = json.loads((method_output / "signature_scores.json").read_text())
        method_results.append(
            _evaluate_method(summary, policy, method_output / "signature_scores.json")
        )

    passing = {item["method"] for item in method_results if item["passed"]}
    preference_order = policy["default_method_policy"]["preference_order"]
    selected = next((method for method in preference_order if method in passing), None)
    recommended = policy["default_method_policy"]["recommended_method"]
    default_repeat_identical = False
    if selected == recommended:
        repeat_output = output_dir / f"{recommended}_repeat"
        repeat_config = SignatureScoringConfig.from_json(output_dir / f"{recommended}_request.json")
        run_signature_scoring(bundle, repeat_config, repeat_output)
        default_repeat_identical = (
            output_dir / recommended / "signature_scores.json"
        ).read_bytes() == (repeat_output / "signature_scores.json").read_bytes()
    thresholds = policy["acceptance_thresholds"]
    eligible = (
        selected == recommended
        and mapping_report["mapping_coverage"]
        >= policy["default_method_policy"]["minimum_mapping_coverage_for_recommendation"]
        and (default_repeat_identical or not thresholds["require_byte_identical_default_rerun"])
    )
    result = {
        "schema_version": "1.0.0",
        "benchmark_id": policy["benchmark_id"],
        "policy_sha256": policy_sha256,
        "dataset": {
            "accession": policy["dataset"]["accession"],
            "superseries_accession": policy["dataset"]["superseries_accession"],
            "platform": policy["dataset"]["platform"],
            "sample_count": policy["dataset"]["sample_count"],
            "expression_bundle_sha256": bundle_sha256,
        },
        "signature": {
            "sha256": signature_sha256,
            "set_count": len(mapping_report["sets"]),
            "requested_identifier_count": mapping_report["requested_identifier_count"],
            "mapped_identifier_count": mapping_report["mapped_identifier_count"],
            "mapping_coverage": mapping_report["mapping_coverage"],
            "mapping_report_sha256": mapping_sha256,
        },
        "thresholds": thresholds,
        "methods": method_results,
        "recommendation": {
            "method": selected or recommended,
            "eligible": eligible,
            "selection_rule": policy["default_method_policy"]["rationale"],
            "default_rerun_byte_identical": default_repeat_identical,
            "raw_cross_cohort_threshold_permitted": False,
        },
        "limitations": [
            policy["signature"]["validation_scope"],
            (
                "Eight samples from four paired donors provide a technical benchmark, not a "
                "population-level clinical validation."
            ),
            (
                "Method selection is governed by a frozen preference order, not by choosing the "
                "largest observed effect after scoring."
            ),
            (
                "No raw signature-score cutoff transfers to another cohort, platform, or "
                "preprocessing pipeline."
            ),
        ],
        "passed": eligible,
    }
    schema = json.loads((ROOT / "schemas/public_signature_benchmark.schema.json").read_text())
    Draft202012Validator(schema).validate(result)
    (output_dir / "public_signature_benchmark.json").write_bytes(_json_bytes(result))
    if not eligible:
        raise AssertionError("No method satisfied the frozen public-benchmark default policy.")
    return result


def _read_gmt(path: Path) -> list[dict[str, Any]]:
    sets = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 4:
                raise ValueError("Each benchmark GMT set requires at least two identifiers.")
            sets.append({"signature_id": fields[0], "name": fields[0], "genes": fields[2:]})
    return sets


def _bundle_features(bundle: Path) -> set[str]:
    with tarfile.open(bundle, "r:gz") as archive:
        manifest_source = archive.extractfile("expression_bundle/bundle_manifest.json")
        if manifest_source is None:
            raise ValueError("Expression Bundle manifest is unreadable.")
        manifest = json.load(manifest_source)
        member = archive.extractfile(f"expression_bundle/{manifest['feature_metadata']}")
        if member is None:
            raise ValueError("Expression Bundle feature metadata is unreadable.")
        text = io.TextIOWrapper(member, encoding="utf-8", newline="")
        return {str(row["feature_id"]) for row in csv.DictReader(text, delimiter="\t")}


def _mapping_report(
    signature_sha256: str,
    bundle_sha256: str,
    signature_sets: list[dict[str, Any]],
    available_features: set[str],
) -> dict[str, Any]:
    mapped_sets = []
    requested_total = 0
    mapped_total = 0
    for signature_set in signature_sets:
        requested = list(signature_set["genes"])
        mapped = [gene for gene in requested if gene in available_features]
        requested_total += len(requested)
        mapped_total += len(mapped)
        mapped_sets.append(
            {
                "signature_id": signature_set["signature_id"],
                "name": signature_set["name"],
                "requested_identifier_count": len(requested),
                "mapped_identifier_count": len(mapped),
                "mapping_coverage": len(mapped) / len(requested),
                "mapped_entries": [
                    {"identifier": gene, "feature_id": gene, "weight": 1.0} for gene in mapped
                ],
            }
        )
    return {
        "signature_definition_id": "gse39795-cartilage-zone-markers",
        "signature_definition_sha256": signature_sha256,
        "expression_bundle_sha256": bundle_sha256,
        "mapping_coverage": mapped_total / requested_total,
        "requested_identifier_count": requested_total,
        "mapped_identifier_count": mapped_total,
        "missing_identifier_count": requested_total - mapped_total,
        "ambiguous_identifier_count": 0,
        "duplicate_identifier_count": 0,
        "sets": mapped_sets,
    }


def _request(
    method: str,
    mapping_sha256: str,
    mapping_report: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    phenotype = policy["phenotype"]
    return {
        "schema_version": "1.0.0",
        "analysis_id": f"public-benchmark-{method}",
        "prepared_dataset_id": "gse39795-public-benchmark",
        "analysis_type": "signature",
        "method": method,
        "assay": "log_expression",
        "parameters": {
            "signature_mapping_id": "gse39795-cartilage-zone-mapping",
            "minimum_gene_set_size": 2,
            "maximum_gene_set_size": 500,
            "gsva_kcdf": "Gaussian",
            "gsva_tau": 1.0,
            "gsva_max_diff": True,
            "gsva_abs_ranking": False,
            "ssgsea_alpha": 0.25,
            "ssgsea_normalize": True,
            "phenotype_association": {
                "enabled": True,
                "phenotype_column": phenotype["column"],
                "phenotype_kind": "categorical",
                "covariates": [],
                "block_column": phenotype["block_column"],
            },
        },
        "signature_mapping": {
            "id": "gse39795-cartilage-zone-mapping",
            "report_sha256": mapping_sha256,
            "report": mapping_report,
        },
        "random_seed": 0,
    }


def _write_request(output_dir: Path, method: str, request: dict[str, Any]) -> Path:
    path = output_dir / f"{method}_request.json"
    path.write_bytes(_json_bytes(request))
    return path


def _evaluate_method(
    summary: dict[str, Any], policy: dict[str, Any], score_path: Path
) -> dict[str, Any]:
    thresholds = policy["acceptance_thresholds"]
    expected = policy["expected_directions"]
    association = {
        item["signature_id"]: item for item in summary["phenotype_association"]["associations"]
    }
    set_results = []
    for signature_set in summary["sets"]:
        signature_id = signature_set["signature_id"]
        scores = signature_set["scores"]
        deep = [item["score"] for item in scores if item["metadata"]["zone"] == "deep"]
        superficial = [
            item["score"] for item in scores if item["metadata"]["zone"] == "superficial"
        ]
        if min(len(deep), len(superficial)) < thresholds["minimum_samples_per_group"]:
            raise ValueError("Public benchmark does not meet its frozen replication threshold.")
        effect = sum(superficial) / len(superficial) - sum(deep) / len(deep)
        direction = expected[signature_id]
        auc = _directional_auc(superficial, deep, direction)
        statistic = association[signature_id]
        direction_passed = effect > 0 if direction == "positive" else effect < 0
        passed = (
            signature_set["mapping_coverage"] >= thresholds["minimum_mapping_coverage"]
            and direction_passed
            and auc >= thresholds["minimum_directional_auc"]
            and statistic["adjusted_p_value"] <= thresholds["maximum_adjusted_p_value"]
        )
        set_results.append(
            {
                "signature_id": signature_id,
                "expected_direction": direction,
                "observed_effect": effect,
                "directional_auc": auc,
                "p_value": statistic["p_value"],
                "adjusted_p_value": statistic["adjusted_p_value"],
                "mapping_coverage": signature_set["mapping_coverage"],
                "passed": passed,
            }
        )
    return {
        "method": summary["method"],
        "runtime": summary["software"]["language"],
        "result_sha256": hashlib.sha256(score_path.read_bytes()).hexdigest(),
        "sets": set_results,
        "passed": all(item["passed"] for item in set_results),
    }


def _directional_auc(numerator: list[float], denominator: list[float], direction: str) -> float:
    wins = 0.0
    for numerator_value in numerator:
        for denominator_value in denominator:
            if numerator_value == denominator_value:
                wins += 0.5
            elif (numerator_value > denominator_value) == (direction == "positive"):
                wins += 1.0
    return wins / (len(numerator) * len(denominator))


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--r-runner", type=Path)
    arguments = parser.parse_args()
    result = run_benchmark(arguments.bundle, arguments.output_dir, r_runner=arguments.r_runner)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
