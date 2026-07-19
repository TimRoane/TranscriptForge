"""Seed a complete synthetic assay lifecycle through TranscriptForge's public API."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from demo.assay_development.complete_demo import DATASET_NAMES, generate_complete_demo
from demo.large_experiment.seed import TERMINAL_STATES, APIClient, _named

PROJECT_NAME = "TranscriptForge Complete Synthetic Assay Development"
ASSAY_NAME = "Synthetic FFPE response classifier endpoint"
INVALID_EXPERIMENT_NAME = "Feasibility teaching draft — confounded revision"
REPAIRED_EXPERIMENT_NAME = "Feasibility input series — balanced revision"
OPTIMIZATION_EXPERIMENT_NAME = "Paired library-method optimization"
PCA_NAME = "Development cohort guided PCA"
DE_NAME = "Development cohort case-control differential expression"
CLASSIFIER_NAME = "Synthetic FFPE response elastic-net classifier — portfolio"
PRECISION_STUDY_NAME = "Locked classifier precision and reproducibility"
ROBUSTNESS_STUDY_NAME = "Locked classifier robustness challenges"
CONFIG_VERSION = "complete-assay-demo-v1"


class SeedConflictError(RuntimeError):
    """An existing stable-name resource disagrees with the frozen demo configuration."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


class CompleteAssaySeeder:
    """Checkpointed, idempotent API orchestration for the portfolio-grade demo."""

    def __init__(
        self,
        client: APIClient,
        source_dir: Path,
        summary_path: Path,
        *,
        web_base: str = "http://localhost:5173",
        poll_seconds: float = 1.0,
        timeout_seconds: int = 3_600,
    ) -> None:
        self.client = client
        self.source_dir = source_dir
        self.summary_path = summary_path
        self.web_base = web_base.rstrip("/")
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.started = time.monotonic()
        self.previous_summary: dict[str, Any] = {}
        if summary_path.exists():
            try:
                previous = json.loads(summary_path.read_text(encoding="utf-8"))
                if isinstance(previous, dict):
                    self.previous_summary = previous
            except (OSError, json.JSONDecodeError):
                pass
        self.summary: dict[str, Any] = {
            "schema_version": "1.0.0",
            "configuration_version": CONFIG_VERSION,
            "status": "RUNNING",
            "synthetic": True,
            "research_use_only": True,
            "datasets": {},
            "experiments": {},
            "analyses": {},
            "models": {},
            "studies": {},
            "decisions": [],
            "urls": {},
            "errors": [],
        }
        previous_runtime = dict(self.previous_summary.get("runtime_evidence") or {})
        previous_elapsed = self.previous_summary.get("elapsed_seconds")
        if (
            self.previous_summary.get("status") == "COMPLETE"
            and isinstance(previous_elapsed, int | float)
            and previous_elapsed >= 10
        ):
            previous_runtime.setdefault("clean_seed_seconds", previous_elapsed)
        if previous_runtime:
            self.summary["runtime_evidence"] = previous_runtime

    def record_runtime_evidence(self) -> None:
        current = round(time.monotonic() - self.started, 3)
        evidence = dict(self.previous_summary.get("runtime_evidence") or {})
        previous_elapsed = self.previous_summary.get("elapsed_seconds")
        if isinstance(previous_elapsed, int | float) and previous_elapsed >= 10:
            evidence.setdefault("clean_seed_seconds", previous_elapsed)
        if current >= 10:
            evidence["clean_seed_seconds"] = current
        else:
            evidence["cached_seed_seconds"] = current
        evidence["workstation_cpu_count"] = os.cpu_count()
        evidence["workstation_specific"] = True
        self.summary["runtime_evidence"] = evidence

    def checkpoint(self) -> None:
        self.summary["elapsed_seconds"] = round(time.monotonic() - self.started, 3)
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.summary_path.with_suffix(self.summary_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, self.summary_path)

    def wait_for_run(self, run_id: str, label: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_seconds
        previous = ""
        while time.monotonic() < deadline:
            run = dict(self.client.request("GET", f"/runs/{run_id}"))
            if run["state"] != previous:
                print(f"{label}: {run['state']}", flush=True)
                previous = str(run["state"])
            if run["state"] in TERMINAL_STATES:
                if run["state"] != "SUCCEEDED":
                    message = run.get("error_summary") or str(run["state"])
                    raise RuntimeError(f"{label} failed in run {run_id}: {message}")
                return run
            time.sleep(self.poll_seconds)
        raise TimeoutError(f"Timed out after {self.timeout_seconds}s waiting for {label}.")

    def _resume_latest_run(self, path: str, label: str) -> dict[str, Any] | None:
        runs = list(self.client.request("GET", path))
        if not runs:
            return None
        latest = runs[0]
        if latest["state"] in {"CREATED", "QUEUED", "STARTING", "RUNNING", "CANCELLING"}:
            return self.wait_for_run(str(latest["id"]), label)
        if latest["state"] == "SUCCEEDED":
            return dict(latest)
        return None

    def ensure_project(self, manifest_sha: str) -> dict[str, Any]:
        expected_description = (
            "Portfolio-grade, fully synthetic assay lifecycle demonstration. "
            f"Configuration {CONFIG_VERSION}; generation manifest SHA-256 {manifest_sha}. "
            "Research use only; no clinical performance claim."
        )
        project = _named(list(self.client.request("GET", "/projects")), PROJECT_NAME)
        if project is None:
            project = dict(
                self.client.request(
                    "POST",
                    "/projects",
                    {"name": PROJECT_NAME, "description": expected_description},
                )
            )
        elif project.get("description") != expected_description:
            raise SeedConflictError(
                f"Existing project '{PROJECT_NAME}' has an incompatible configuration marker."
            )
        self.summary["project_id"] = project["id"]
        self.summary["urls"]["project"] = f"{self.web_base}/projects/{project['id']}"
        self.checkpoint()
        return dict(project)

    def ensure_dataset(
        self,
        project_id: str,
        key: str,
        generation: dict[str, Any],
    ) -> str:
        dataset_dir = self.source_dir / key
        checksum = _canonical_sha(generation)
        annotation_release = f"synthetic-e2e-v1-{checksum[:16]}"
        existing = _named(
            list(self.client.request("GET", f"/projects/{project_id}/datasets")),
            DATASET_NAMES[key],
        )
        if existing is None:
            existing = dict(
                self.client.request(
                    "POST",
                    f"/projects/{project_id}/datasets",
                    {
                        "name": DATASET_NAMES[key],
                        "description": (
                            f"Synthetic {key} evidence; {generation['measurement_count']} "
                            f"measurements over {generation['feature_count']} shared Ensembl "
                            "features."
                        ),
                        "modality": "bulk_rnaseq",
                        "source_kind": "count_matrix",
                        "genome_build": "GRCh38",
                        "annotation_release": annotation_release,
                    },
                )
            )
        if existing.get("annotation_release") != annotation_release:
            raise SeedConflictError(
                f"Dataset '{DATASET_NAMES[key]}' exists with an incompatible checksum marker."
            )
        dataset_id = str(existing["id"])
        files = list(self.client.request("GET", f"/datasets/{dataset_id}/files"))
        by_role = {item["role"]: item for item in files}
        for role, filename in (
            ("count_matrix", "counts.tsv"),
            ("sample_metadata", "sample_metadata.tsv"),
        ):
            path = dataset_dir / filename
            present = by_role.get(role)
            if present is not None and present["sha256"] != _sha(path):
                raise SeedConflictError(
                    f"Dataset '{DATASET_NAMES[key]}' role '{role}' has different immutable bytes."
                )
            if present is None:
                self.client.upload(dataset_id, role, path)

        prepared = list(self.client.request("GET", f"/datasets/{dataset_id}/prepared-versions"))
        if not prepared:
            current = dict(self.client.request("GET", f"/datasets/{dataset_id}"))
            if current["status"] == "validating":
                self._resume_latest_run(
                    f"/datasets/{dataset_id}/validation-runs", f"{key} validation"
                )
                current = dict(self.client.request("GET", f"/datasets/{dataset_id}"))
            if current["status"] in {"draft", "invalid"}:
                validation = dict(
                    self.client.request(
                        "POST",
                        f"/datasets/{dataset_id}/validate",
                        {
                            "matrix_orientation": "features_by_samples",
                            "feature_id_column": "gene_id",
                            "sample_id_column": "sample_id",
                            "feature_id_type": "ensembl_gene_id",
                        },
                    )
                )
                self.wait_for_run(str(validation["id"]), f"{key} validation")
                current = dict(self.client.request("GET", f"/datasets/{dataset_id}"))
            if current["status"] == "preparing":
                self._resume_latest_run(
                    f"/datasets/{dataset_id}/preparation-runs", f"{key} preparation"
                )
            prepared = list(self.client.request("GET", f"/datasets/{dataset_id}/prepared-versions"))
            if not prepared:
                preparation = dict(self.client.request("POST", f"/datasets/{dataset_id}/prepare"))
                completed = self.wait_for_run(str(preparation["id"]), f"{key} preparation")
                prepared_id = str(completed["prepared_dataset_id"])
            else:
                prepared_id = str(prepared[0]["id"])
        else:
            prepared_id = str(prepared[0]["id"])
        self.summary["datasets"][key] = {
            "dataset_id": dataset_id,
            "prepared_dataset_id": prepared_id,
            "configuration_sha256": checksum,
            "source_checksums": generation["files"],
            "status": "PREPARED",
        }
        self.summary["urls"][f"{key}_bundle"] = f"{self.web_base}/prepared-datasets/{prepared_id}"
        self.checkpoint()
        return prepared_id

    def ensure_assay(self, project_id: str, manifest_sha: str) -> dict[str, Any]:
        expected_version = f"synthetic-e2e-v1-{manifest_sha[:16]}"
        assay = next(
            (
                item
                for item in self.client.request("GET", "/assay-projects")
                if item["project_id"] == project_id
            ),
            None,
        )
        if assay is None:
            assay = self.client.request(
                "POST",
                "/assay-projects",
                {
                    "project_id": project_id,
                    "name": ASSAY_NAME,
                    "proposed_purpose": (
                        "Demonstrate a reproducible research classifier lifecycle from paired "
                        "FFPE feasibility through analytical validation."
                    ),
                    "specimen_type": "synthetic FFPE tumor RNA",
                    "biological_context": (
                        "Known simulated response signal, degradation effects, technical factors, "
                        "borderline specimens, and null features."
                    ),
                    "proposed_output": "locked binary research classifier score and call",
                    "current_stage": "FEASIBILITY",
                    "assay_version": expected_version,
                },
            )
        if assay.get("assay_version") != expected_version:
            raise SeedConflictError(
                f"Assay project '{ASSAY_NAME}' has an incompatible configuration marker."
            )
        self.summary["assay_project_id"] = assay["id"]
        self.summary["urls"]["dashboard"] = f"{self.web_base}/assay-development/{assay['id']}"
        self.checkpoint()
        return dict(assay)

    def ensure_question(self, assay_id: str, key: str, formal_question: str) -> dict[str, Any]:
        questions = list(self.client.request("GET", f"/assay-projects/{assay_id}/questions"))
        existing = next(
            (
                item
                for item in questions
                if item["question_key"] == key and item["formal_question"] == formal_question
            ),
            None,
        )
        if existing is not None:
            return dict(existing)
        return dict(
            self.client.request(
                "POST",
                f"/assay-projects/{assay_id}/questions",
                {
                    "question_key": key,
                    "formal_question": formal_question,
                    "source": "USER_SELECTED",
                },
            )
        )

    def accept_route(self, assay_id: str, action_type: str, rationale: str) -> None:
        recommendations = list(
            self.client.request("GET", f"/assay-projects/{assay_id}/recommendations")
        )
        candidate = next(
            (
                item
                for item in recommendations
                if item["status"] == "OPEN"
                and item["proposed_action"].get("action_type") == action_type
            ),
            None,
        )
        if candidate is None:
            return
        self.client.request(
            "POST",
            f"/recommendations/{candidate['id']}/accept",
            {"rationale": rationale},
        )
        self.summary["decisions"].append(
            {"type": "recommendation", "recommendation_id": candidate["id"], "decision": "ACCEPT"}
        )
        self.checkpoint()

    def _experiment_assignments(
        self,
        key: str,
        prepared_id: str,
        *,
        confounded: bool = False,
    ) -> list[dict[str, Any]]:
        assignments: list[dict[str, Any]] = []
        for row in _rows(self.source_dir / key / "sample_metadata.tsv"):
            if key == "feasibility":
                run = f"run_input_{row['input_ng']}" if confounded else row["sequencing_run"]
                assignments.append(
                    {
                        "measurement_id": row["sample_id"],
                        "biological_sample_id": row["biological_sample_id"],
                        "prepared_dataset_id": prepared_id,
                        "include": True,
                        "replicate_id": row["input_ng"],
                        "pair_id": row["biological_sample_id"],
                        "input_ng": float(row["input_ng"]),
                        "dv200": float(row["dv200"]),
                        "sequencing_run": run,
                        "operator": row["operator"],
                        "reagent_lot": row["reagent_lot"],
                        "instrument": row["instrument"],
                        "processing_order": int(row["processing_order"]),
                    }
                )
            else:
                assignments.append(
                    {
                        "measurement_id": row["sample_id"],
                        "biological_sample_id": row["biological_sample_id"],
                        "prepared_dataset_id": prepared_id,
                        "include": True,
                        "replicate_id": row["condition"],
                        "pair_id": row["pair_id"],
                        "condition": row["condition"],
                        "run": row["sequencing_run"],
                        "operator": row["operator"],
                        "reagent_lot": row["reagent_lot"],
                        "quality_metric": float(row["quality_metric"]),
                        "processing_order": int(row["processing_order"]),
                        "library_method": row["library_method"],
                    }
                )
        return assignments

    def ensure_feasibility_lineage(
        self, assay_id: str, question_id: str, prepared_id: str
    ) -> dict[str, Any]:
        experiments = list(self.client.request("GET", f"/assay-projects/{assay_id}/experiments"))
        invalid = _named(experiments, INVALID_EXPERIMENT_NAME)
        if invalid is None:
            invalid = dict(
                self.client.request(
                    "POST",
                    "/experiments",
                    {
                        "assay_project_id": assay_id,
                        "question_id": question_id,
                        "prepared_dataset_id": prepared_id,
                        "name": INVALID_EXPERIMENT_NAME,
                        "objective": "Teach detection of input-by-run confounding before analysis.",
                        "experiment_type": "INPUT_DEGRADATION_EXPLORATION",
                        "mode": "ANALYZE_EXISTING",
                        "reference_level": 100,
                        "assay": "log_expression",
                        "declared_questions": [
                            "Does input remain interpretable after run blocking?"
                        ],
                        "reference_level_rationale": "100 ng is the prespecified reference input.",
                        "endpoint_rationale": (
                            "Paired profile stability and detected genes expose degradation "
                            "effects."
                        ),
                        "assignments": self._experiment_assignments(
                            "feasibility", prepared_id, confounded=True
                        ),
                    },
                )
            )
        if invalid["status"] == "DRAFT":
            invalid = dict(
                self.client.request("POST", f"/experiments/{invalid['id']}/validate-design")
            )
        if invalid["status"] != "DESIGN_INVALID":
            raise SeedConflictError("The teaching revision is no longer invalid as prescribed.")
        blocking_codes = {item["code"] for item in invalid["design_validation"].get("errors", [])}
        if blocking_codes != {"DESIGN.INPUT_RUN_CONFOUNDED"}:
            raise SeedConflictError(
                f"Teaching revision has unexpected blocking findings: {sorted(blocking_codes)}"
            )

        repaired = _named(experiments, REPAIRED_EXPERIMENT_NAME)
        if repaired is None:
            repaired = dict(self.client.request("POST", f"/experiments/{invalid['id']}/clone"))
            repaired = dict(
                self.client.request(
                    "PATCH",
                    f"/experiments/{repaired['id']}",
                    {
                        "name": REPAIRED_EXPERIMENT_NAME,
                        "objective": (
                            "Recover paired input effects after crossing input levels over runs, "
                            "operators, and reagent lots."
                        ),
                        "assignments": self._experiment_assignments("feasibility", prepared_id),
                    },
                )
            )
        repaired = self._run_experiment(repaired, "balanced feasibility experiment")
        self.summary["experiments"]["teaching_draft"] = {
            "id": invalid["id"],
            "status": invalid["status"],
            "blocking_codes": sorted(blocking_codes),
        }
        self.summary["experiments"]["repaired_feasibility"] = {
            "id": repaired["id"],
            "status": repaired["status"],
            "parent_experiment_id": repaired["parent_experiment_id"],
            "revision": repaired["current_revision"],
        }
        self.summary["urls"]["teaching_draft"] = f"{self.web_base}/experiments/{invalid['id']}"
        self.summary["urls"]["repaired_experiment"] = (
            f"{self.web_base}/experiments/{repaired['id']}"
        )
        self.checkpoint()
        return repaired

    def _run_experiment(self, experiment: dict[str, Any], label: str) -> dict[str, Any]:
        status = experiment["status"]
        if status == "DRAFT" or status == "DESIGN_INVALID":
            experiment = dict(
                self.client.request("POST", f"/experiments/{experiment['id']}/validate-design")
            )
        if experiment["status"] == "DESIGN_INVALID":
            codes = [item["code"] for item in experiment["design_validation"]["findings"]]
            raise RuntimeError(f"{label} design is invalid: {codes}")
        if experiment["status"] == "DESIGN_VALID":
            experiment = dict(
                self.client.request(
                    "POST", f"/experiments/{experiment['id']}/lock-execution-revision"
                )
            )
        if experiment["status"] in {"QUEUED", "RUNNING"}:
            results = dict(self.client.request("GET", f"/experiments/{experiment['id']}/results"))
            if results["run_id"]:
                self.wait_for_run(str(results["run_id"]), label)
        elif experiment["status"] == "LOCKED_FOR_EXECUTION":
            response = dict(self.client.request("POST", f"/experiments/{experiment['id']}/run"))
            self.wait_for_run(str(response["run_id"]), label)
        elif experiment["status"] in {"FAILED", "CANCELLED"}:
            raise RuntimeError(
                f"{label} is {experiment['status']}; clone or repair it before resuming."
            )
        return dict(self.client.request("GET", f"/experiments/{experiment['id']}"))

    def ensure_optimization(
        self, assay_id: str, question_id: str, prepared_id: str
    ) -> dict[str, Any]:
        experiments = list(self.client.request("GET", f"/assay-projects/{assay_id}/experiments"))
        experiment = _named(experiments, OPTIMIZATION_EXPERIMENT_NAME)
        if experiment is None:
            experiment = dict(
                self.client.request(
                    "POST",
                    "/experiments",
                    {
                        "assay_project_id": assay_id,
                        "question_id": question_id,
                        "prepared_dataset_id": prepared_id,
                        "name": OPTIMIZATION_EXPERIMENT_NAME,
                        "objective": (
                            "Compare the candidate and reference library methods within specimen."
                        ),
                        "experiment_type": "PAIRED_CONDITION_COMPARISON",
                        "mode": "ANALYZE_EXISTING",
                        "reference_condition": "reference",
                        "comparator_condition": "candidate",
                        "assay": "log_expression",
                        "primary_endpoints": ["paired_bias", "profile_correlation"],
                        "secondary_endpoints": ["detected_gene_difference", "discordance"],
                        "declared_questions": [
                            "Does the candidate method preserve the reference profile?"
                        ],
                        "condition_contrast_rationale": (
                            "The established method is the paired reference."
                        ),
                        "endpoint_rationale": (
                            "Bias, agreement, detection, and discordance are complementary."
                        ),
                        "assignments": self._experiment_assignments("optimization", prepared_id),
                    },
                )
            )
        experiment = self._run_experiment(dict(experiment), "paired optimization experiment")
        self.summary["experiments"]["optimization"] = {
            "id": experiment["id"],
            "status": experiment["status"],
            "revision": experiment["current_revision"],
        }
        self.summary["urls"]["optimization_experiment"] = (
            f"{self.web_base}/experiments/{experiment['id']}"
        )
        self.checkpoint()
        return experiment

    def ensure_analysis(
        self,
        prepared_id: str,
        name: str,
        payload: dict[str, Any],
        label: str,
    ) -> dict[str, Any]:
        expected_sha = _canonical_sha(payload)
        tagged_payload = {
            **payload,
            "name": name,
            "description": (
                f"Fully synthetic research-use demonstration. Config SHA-256 {expected_sha}."
            ),
        }
        analyses = list(self.client.request("GET", f"/prepared-datasets/{prepared_id}/analyses"))
        analysis = _named(analyses, name)
        if analysis is None:
            analysis = dict(
                self.client.request(
                    "POST", f"/prepared-datasets/{prepared_id}/analyses", tagged_payload
                )
            )
        elif expected_sha not in str(analysis.get("description")):
            raise SeedConflictError(f"Analysis '{name}' has an incompatible configuration.")
        runs = list(self.client.request("GET", f"/analyses/{analysis['id']}/runs"))
        successful = next((run for run in runs if run["state"] == "SUCCEEDED"), None)
        if successful is None:
            active = next(
                (
                    run
                    for run in runs
                    if run["state"] in {"CREATED", "QUEUED", "STARTING", "RUNNING", "CANCELLING"}
                ),
                None,
            )
            if active is not None:
                successful = self.wait_for_run(str(active["id"]), label)
            elif any(run["state"] == "FAILED" for run in runs):
                raise RuntimeError(f"{label} has a failed run; inspect it before resuming.")
            else:
                # Cancellation preserves the frozen request and is safe to rerun explicitly.
                launched = dict(self.client.request("POST", f"/analyses/{analysis['id']}/run"))
                successful = self.wait_for_run(str(launched["id"]), label)
        self.summary["analyses"][label] = {
            "analysis_id": analysis["id"],
            "run_id": successful["id"],
            "status": successful["state"],
            "configuration_sha256": expected_sha,
        }
        self.summary["urls"][label] = f"{self.web_base}/analyses/{analysis['id']}"
        self.checkpoint()
        return analysis

    def ensure_model(self, analysis_id: str) -> dict[str, Any]:
        models = list(self.client.request("GET", f"/analyses/{analysis_id}/models"))
        if not models:
            raise RuntimeError(
                "Classifier execution succeeded without a registered model candidate."
            )
        model = dict(models[0])
        if model["status"] == "CANDIDATE":
            model = dict(
                self.client.request(
                    "POST",
                    f"/models/{model['id']}/review",
                    {
                        "rationale": (
                            "Reviewed group-safe nested CV, complete OOF predictions, permutation "
                            "evidence, serialization, intended use, and research-only limitations."
                        )
                    },
                )
            )
        if model["status"] == "REVIEWED":
            readiness = dict(self.client.request("GET", f"/models/{model['id']}/lock-readiness"))
            if not readiness["ready"]:
                raise RuntimeError(f"Model lock readiness failed: {readiness['blockers']}")
            model = dict(
                self.client.request(
                    "POST",
                    f"/models/{model['id']}/lock",
                    {
                        "rationale": (
                            "Freeze the eligible synthetic research model before independent "
                            "precision and robustness evaluation."
                        )
                    },
                )
            )
        if model["status"] != "LOCKED":
            raise RuntimeError(f"Expected a locked model, found {model['status']}.")
        integrity = dict(self.client.request("POST", f"/models/{model['id']}/integrity"))
        if not integrity["valid"]:
            raise RuntimeError(f"Locked model integrity failed: {integrity['errors']}")
        self.summary["models"]["locked_classifier"] = {
            "model_id": model["id"],
            "status": model["status"],
            "model_manifest_sha256": model["model_manifest_sha256"],
            "model_package_sha256": model["model_package_sha256"],
            "inference_test_status": model["inference_test_status"],
            "integrity_valid": True,
        }
        self.summary["urls"]["locked_model"] = f"{self.web_base}/models/{model['id']}"
        self.checkpoint()
        return model

    def _study_assignments(self, key: str) -> list[dict[str, Any]]:
        assignments: list[dict[str, Any]] = []
        for row in _rows(self.source_dir / key / "sample_metadata.tsv"):
            if key == "precision":
                assignments.append(
                    {
                        "measurement_id": row["sample_id"],
                        "biological_sample_id": row["biological_sample_id"],
                        "replicate_id": row["replicate_id"],
                        "operator": row["operator"],
                        "run": row["run"],
                        "reagent_lot": row["reagent_lot"],
                        "instrument": row["instrument"],
                        "day": row["day"],
                        "qc_failure": row["qc_failure"] == "true",
                        "include": True,
                    }
                )
            else:
                assignments.append(
                    {
                        "measurement_id": row["sample_id"],
                        "biological_sample_id": row["biological_sample_id"],
                        "replicate_id": row["condition"],
                        "condition": row["condition"],
                        "challenge_type": row["challenge_type"],
                        "run": row["run"],
                        "operator": row["operator"],
                        "reagent_lot": row["reagent_lot"],
                        "subgroup": row["subgroup"],
                        "qc_failure": row["qc_failure"] == "true",
                        "include": True,
                    }
                )
        return assignments

    def ensure_study(
        self,
        assay_id: str,
        question_id: str,
        model_id: str,
        prepared_id: str,
        *,
        key: str,
        name: str,
    ) -> dict[str, Any]:
        studies = list(self.client.request("GET", f"/assay-projects/{assay_id}/studies"))
        study = _named(studies, name)
        if study is None:
            template: dict[str, Any]
            if key == "precision":
                template = {
                    "study_type": "PRECISION_REPRODUCIBILITY",
                    "objective": (
                        "Quantify locked-score repeatability and reproducibility without "
                        "retraining."
                    ),
                    "factors": ["operator", "run", "reagent_lot", "instrument", "day"],
                    "criteria": [
                        {
                            "key": "score_icc",
                            "metric": "icc",
                            "endpoint": "classifier_score",
                            "operator": "gte",
                            "threshold": 0.80,
                            "rationale": "Prespecified strong score reliability target.",
                        },
                        {
                            "key": "call_agreement",
                            "metric": "categorical_agreement",
                            "endpoint": "predicted_class",
                            "operator": "gte",
                            "threshold": 0.90,
                            "rationale": "Replicate calls should remain highly concordant.",
                        },
                        {
                            "key": "qc_failure_rate",
                            "metric": "qc_failure_rate",
                            "endpoint": "qc_failure",
                            "operator": "lte",
                            "threshold": 0.10,
                            "rationale": "Technical QC failures must remain uncommon.",
                        },
                    ],
                }
            else:
                template = {
                    "study_type": "ROBUSTNESS_INTERFERENCE",
                    "objective": (
                        "Measure locked-score changes under prespecified synthetic challenges "
                        "without retraining."
                    ),
                    "factors": ["condition", "challenge_type", "run", "subgroup"],
                    "reference_condition": "reference",
                    "comparator_condition": "challenge",
                    "equivalence_margin": 0.15,
                    "condition_rationale": (
                        "Unchallenged aliquots are the paired locked-endpoint reference."
                    ),
                    "criteria": [
                        {
                            "key": "challenge_effect",
                            "metric": "mean_challenge_effect",
                            "endpoint": "classifier_score",
                            "operator": "absolute_lte",
                            "threshold": 0.15,
                            "rationale": (
                                "Mean challenge effect must remain within the prespecified "
                                "score margin."
                            ),
                        },
                        {
                            "key": "call_change",
                            "metric": "call_change_rate",
                            "endpoint": "predicted_class",
                            "operator": "lte",
                            "threshold": 0.10,
                            "rationale": "Challenge-associated call changes must remain uncommon.",
                        },
                        {
                            "key": "qc_failure_rate",
                            "metric": "qc_failure_rate",
                            "endpoint": "qc_failure",
                            "operator": "lte",
                            "threshold": 0.10,
                            "rationale": "Challenge-associated QC failures must remain uncommon.",
                        },
                    ],
                }
            study = dict(
                self.client.request(
                    "POST",
                    "/studies",
                    {
                        "assay_project_id": assay_id,
                        "question_id": question_id,
                        "model_id": model_id,
                        "prepared_dataset_id": prepared_id,
                        "name": name,
                        "assignments": self._study_assignments(key),
                        "confidence_level": 0.95,
                        "bootstrap_iterations": 200,
                        "threshold_proximity_band": 0.10,
                        **template,
                    },
                )
            )
        if study["status"] == "DESIGN_INVALID" and key == "precision":
            study = dict(
                self.client.request(
                    "PATCH",
                    f"/studies/{study['id']}",
                    {"factors": ["operator", "run", "reagent_lot"]},
                )
            )
        if study["status"] in {"DRAFT", "DESIGN_INVALID"}:
            study = dict(self.client.request("POST", f"/studies/{study['id']}/validate-design"))
        if study["status"] == "DESIGN_INVALID":
            raise RuntimeError(
                f"Study '{name}' design is invalid: {study['design_validation_json']}"
            )
        if study["status"] == "DESIGN_VALID":
            study = dict(self.client.request("POST", f"/studies/{study['id']}/lock"))
        if study["status"] in {"QUEUED", "RUNNING"}:
            results = dict(self.client.request("GET", f"/studies/{study['id']}/results"))
            if results["run_id"]:
                self.wait_for_run(str(results["run_id"]), name)
        elif study["status"] == "LOCKED":
            launched = dict(self.client.request("POST", f"/studies/{study['id']}/run"))
            self.wait_for_run(str(launched["run_id"]), name)
        elif study["status"] in {"FAILED", "CANCELLED"}:
            raise RuntimeError(f"Study '{name}' is {study['status']}; inspect it before resuming.")
        study = dict(self.client.request("GET", f"/studies/{study['id']}"))
        results = dict(self.client.request("GET", f"/studies/{study['id']}/results"))
        summary = results.get("summary") or {}
        if summary and summary.get("model_retrained") is not False:
            raise RuntimeError(f"Study '{name}' did not preserve the no-retraining boundary.")
        self.summary["studies"][key] = {
            "study_id": study["id"],
            "status": study["status"],
            "validation_bundle_uri": study["validation_bundle_uri"],
            "model_retrained": summary.get("model_retrained"),
            "overall_status": summary.get("overall_status"),
        }
        self.summary["urls"][f"{key}_study"] = f"{self.web_base}/studies/{study['id']}"
        self.checkpoint()
        return study

    def advance_to_report(self, assay_id: str) -> None:
        assay = dict(self.client.request("GET", f"/assay-projects/{assay_id}"))
        stages = ["EXPLORE", "OPTIMIZE", "DEVELOP", "LOCK", "VALIDATE", "REPORT"]
        current_index = (
            stages.index(assay["current_stage"]) if assay["current_stage"] in stages else -1
        )
        for stage in stages[current_index + 1 :]:
            decision = dict(
                self.client.request(
                    "POST",
                    f"/assay-projects/{assay_id}/stage-decisions",
                    {
                        "requested_stage": stage,
                        "decision": "ACCEPT",
                        "rationale": (
                            f"Advance the synthetic demonstration to {stage} after reviewing "
                            "the linked immutable evidence; this is a scripted research-demo "
                            "decision."
                        ),
                    },
                )
            )
            self.summary["decisions"].append(
                {"type": "stage", "decision_id": decision["id"], "requested_stage": stage}
            )
            self.checkpoint()

    def verify_synthetic_expectations(self) -> None:
        """Fail completion if the real workflow does not recover the declared demo truth."""

        feasibility = dict(
            self.client.request(
                "GET",
                f"/experiments/{self.summary['experiments']['repaired_feasibility']['id']}/results",
            )
        )["decision_summary"]
        feasibility_conditions = {
            float(item["input_ng"]): item for item in feasibility.get("condition_results", [])
        }
        if set(feasibility_conditions) != {25.0, 50.0, 100.0}:
            raise RuntimeError("Feasibility evidence did not retain all three RNA input levels.")
        high_correlation = float(feasibility_conditions[100.0]["mean_profile_correlation"])
        low_correlation = float(feasibility_conditions[25.0]["mean_profile_correlation"])
        if high_correlation - low_correlation < 0.10:
            raise RuntimeError(
                "Feasibility evidence did not recover the seeded degradation effect."
            )

        optimization = dict(
            self.client.request(
                "GET",
                f"/experiments/{self.summary['experiments']['optimization']['id']}/results",
            )
        )["decision_summary"]
        optimization_result = optimization.get("condition_results", [{}])[0]
        if int(optimization_result.get("pair_count", 0)) != 12:
            raise RuntimeError("Optimization evidence did not retain all 12 exact pairs.")
        if abs(float(optimization_result.get("mean_paired_difference", 1))) > 0.05:
            raise RuntimeError("Optimization evidence exceeded the synthetic mean-shift bound.")
        if float(optimization_result.get("median_profile_correlation", 0)) < 0.85:
            raise RuntimeError(
                "Optimization evidence did not recover the expected profile agreement."
            )

        de_run = self.summary["analyses"]["guided_differential_expression"]["run_id"]
        all_de: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = dict(
                self.client.request(
                    "GET",
                    f"/runs/{de_run}/differential-expression/results?offset={offset}&limit=100",
                )
            )
            all_de.extend(page["items"])
            offset += len(page["items"])
            if offset >= int(page["total"]):
                break
        truth = json.loads((self.source_dir / "synthetic_truth.json").read_text(encoding="utf-8"))
        blocks = truth["truth_blocks"]
        positive = set(blocks["classifier_positive"]["features"])
        negative = set(blocks["classifier_negative"]["features"])
        null = set(blocks["null"]["features"])
        recovered_positive = sum(
            item["feature_id"] in positive
            and item["significant"]
            and float(item["log2_fold_change"]) > 0
            for item in all_de
        )
        recovered_negative = sum(
            item["feature_id"] in negative
            and item["significant"]
            and float(item["log2_fold_change"]) < 0
            for item in all_de
        )
        null_calls = sum(item["feature_id"] in null and item["significant"] for item in all_de)
        if recovered_positive < 36 or recovered_negative < 36 or null_calls > 50:
            raise RuntimeError(
                "Differential expression missed its synthetic recovery bounds: "
                f"positive={recovered_positive}, negative={recovered_negative}, null={null_calls}."
            )

        classifier_run = self.summary["analyses"]["classifier_development"]["run_id"]
        classifier = dict(self.client.request("GET", f"/runs/{classifier_run}/classifier-results"))
        coverage = classifier["oof_coverage"]
        permutations = classifier["permutation_control"]
        if (
            float(classifier["metrics"]["roc_auc"]) < 0.90
            or not coverage["one_prediction_per_sample_per_repeat"]
            or int(coverage["observed_prediction_count"])
            != int(coverage["expected_prediction_count"])
            or int(permutations["count"]) != 100
            or float(permutations["empirical_p_value"]) > 0.05
        ):
            raise RuntimeError(
                "Classifier evidence did not meet the frozen synthetic expectations."
            )

        self.summary["synthetic_expectations"] = {
            "status": "PASS",
            "feasibility_profile_correlation_delta": round(high_correlation - low_correlation, 6),
            "optimization_pair_count": int(optimization_result["pair_count"]),
            "optimization_mean_paired_difference": optimization_result["mean_paired_difference"],
            "de_positive_features_recovered": recovered_positive,
            "de_negative_features_recovered": recovered_negative,
            "de_null_features_called": null_calls,
            "classifier_roc_auc": classifier["metrics"]["roc_auc"],
            "classifier_oof_prediction_count": coverage["observed_prediction_count"],
            "classifier_permutation_count": permutations["count"],
            "classifier_permutation_p_value": permutations["empirical_p_value"],
        }
        self.checkpoint()

    def run(self) -> dict[str, Any]:
        generation = generate_complete_demo(self.source_dir)
        manifest_path = self.source_dir / "generation_manifest.json"
        manifest_sha = _sha(manifest_path)
        self.summary["generation_manifest"] = str(manifest_path)
        self.summary["generation_manifest_sha256"] = manifest_sha
        self.summary["synthetic_truth"] = str(self.source_dir / "synthetic_truth.json")
        self.summary["synthetic_truth_sha256"] = generation["truth_sha256"]
        self.checkpoint()

        project = self.ensure_project(manifest_sha)
        prepared = {
            key: self.ensure_dataset(str(project["id"]), key, generation["datasets"][key])
            for key in ("feasibility", "optimization", "classifier", "precision", "robustness")
        }
        assay = self.ensure_assay(str(project["id"]), manifest_sha)
        assay_id = str(assay["id"])

        feasibility_question = self.ensure_question(
            assay_id,
            "input_degradation_stability",
            "Can paired expression stability remain interpretable at 50 ng and 25 ng after "
            "crossing input levels over technical runs?",
        )
        self.accept_route(
            assay_id,
            "CREATE_EXPERIMENT",
            "The paired feasibility template directly addresses the prespecified input question.",
        )
        self.ensure_feasibility_lineage(
            assay_id, str(feasibility_question["id"]), prepared["feasibility"]
        )

        pca_question = self.ensure_question(
            assay_id,
            "largest_variance_source",
            "Which known biological and technical variables explain the largest structure in "
            "the balanced development cohort?",
        )
        self.accept_route(
            assay_id,
            "CREATE_ANALYSIS",
            "PCA is the constrained exploratory view for the declared variance question.",
        )
        self.ensure_analysis(
            prepared["classifier"],
            PCA_NAME,
            {
                "analysis_type": "dimension_reduction",
                "method": "pca",
                "assay": "log_expression",
                "parameters": {"component_count": 10, "scale_features": False},
                "random_seed": 20_260_718,
                "assay_project_id": assay_id,
                "scientific_question_id": pca_question["id"],
            },
            "guided_pca",
        )

        de_question = self.ensure_question(
            assay_id,
            "differential_expression_signal",
            "Which prespecified expression features differ between synthetic cases and controls "
            "in the balanced development cohort?",
        )
        self.accept_route(
            assay_id,
            "CREATE_ANALYSIS",
            "Differential expression directly addresses the declared case-control signal question.",
        )
        self.ensure_analysis(
            prepared["classifier"],
            DE_NAME,
            {
                "analysis_type": "differential_expression",
                "method": "auto",
                "assay": "raw_counts",
                "parameters": {
                    "design": {
                        "primary_variable": "outcome",
                        "covariates": [],
                        "reference_levels": {"outcome": "control"},
                    },
                    "contrast": {
                        "variable": "outcome",
                        "numerator": "case",
                        "denominator": "control",
                    },
                    "low_count_threshold": 10,
                    "minimum_samples": 2,
                    "fdr_threshold": 0.05,
                    "absolute_log2_fold_change": 0.5,
                    "independent_filtering": True,
                    "shrinkage": True,
                    "enrichment": {"enabled": False},
                },
                "random_seed": 20_260_718,
                "assay_project_id": assay_id,
                "scientific_question_id": de_question["id"],
            },
            "guided_differential_expression",
        )

        optimization_question = self.ensure_question(
            assay_id,
            "paired_condition_performance",
            "Does the candidate library method preserve the reference expression endpoint "
            "within paired specimens?",
        )
        self.accept_route(
            assay_id,
            "CREATE_EXPERIMENT",
            "The paired-condition template matches the prespecified library-method comparison.",
        )
        self.ensure_optimization(
            assay_id, str(optimization_question["id"]), prepared["optimization"]
        )

        classifier_question = self.ensure_question(
            assay_id,
            "classifier_signal",
            "Can the prespecified synthetic outcome be predicted under grouped repeated nested "
            "cross-validation without information leakage?",
        )
        self.accept_route(
            assay_id,
            "CREATE_ANALYSIS",
            "A grouped nested-CV classifier is appropriate for the frozen synthetic outcome.",
        )
        classifier = self.ensure_analysis(
            prepared["classifier"],
            CLASSIFIER_NAME,
            {
                "analysis_type": "classifier",
                "method": "elastic_net",
                "assay": "log_expression",
                "parameters": {
                    "outcome_column": "outcome",
                    "positive_class": "case",
                    "group_column": "patient_id",
                    "cohort_column": "cohort",
                    "top_variable_features": 200,
                    "class_weight": "balanced",
                    "outer_folds": 3,
                    "inner_folds": 2,
                    "repeats": 2,
                    "primary_metric": "roc_auc",
                    "probability_calibration": "none",
                    "decision_threshold_strategy": "fixed_0_5",
                    "bootstrap_iterations": 200,
                    "permutation_count": 100,
                },
                "random_seed": 20_260_718,
                "assay_project_id": assay_id,
                "scientific_question_id": classifier_question["id"],
            },
            "classifier_development",
        )
        model = self.ensure_model(str(classifier["id"]))

        precision_question = self.ensure_question(
            assay_id,
            "precision_reproducibility",
            "Does the frozen classifier retain score and call agreement across crossed "
            "operators, runs, lots, instruments, and days?",
        )
        self.accept_route(
            assay_id,
            "CREATE_STUDY",
            "The crossed replicate panel is appropriate for locked-model precision evidence.",
        )
        self.ensure_study(
            assay_id,
            str(precision_question["id"]),
            str(model["id"]),
            prepared["precision"],
            key="precision",
            name=PRECISION_STUDY_NAME,
        )

        robustness_question = self.ensure_question(
            assay_id,
            "robustness_interference_validation",
            "Do prespecified hemoglobin, freeze-thaw, and low-DV200 challenges change the frozen "
            "classifier beyond declared margins?",
        )
        self.accept_route(
            assay_id,
            "CREATE_STUDY",
            "The paired challenge panel directly addresses the locked-endpoint robustness "
            "question.",
        )
        self.ensure_study(
            assay_id,
            str(robustness_question["id"]),
            str(model["id"]),
            prepared["robustness"],
            key="robustness",
            name=ROBUSTNESS_STUDY_NAME,
        )
        self.verify_synthetic_expectations()
        self.advance_to_report(assay_id)
        final_assay = dict(self.client.request("GET", f"/assay-projects/{assay_id}"))
        if final_assay["current_stage"] != "REPORT":
            raise RuntimeError("The completed demonstration did not reach REPORT stage.")
        self.summary["status"] = "COMPLETE"
        self.summary["final_stage"] = final_assay["current_stage"]
        self.summary["scientific_boundary"] = (
            "All inputs and recovered effects are synthetic; advancement decisions demonstrate "
            "workflow governance and are not clinical or regulatory conclusions."
        )
        self.record_runtime_evidence()
        self.checkpoint()
        return self.summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost:8000/api")
    parser.add_argument("--web-base", default="http://localhost:5173")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".transcriptforge-demo/complete_assay"),
    )
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=3_600)
    arguments = parser.parse_args()
    seeder = CompleteAssaySeeder(
        APIClient(arguments.api_base),
        arguments.output_dir / "source",
        arguments.output_dir / "complete_assay_seed_summary.json",
        web_base=arguments.web_base,
        poll_seconds=arguments.poll_seconds,
        timeout_seconds=arguments.timeout_seconds,
    )
    try:
        result = seeder.run()
    except Exception as error:
        seeder.summary["status"] = "FAILED"
        seeder.summary["errors"].append({"type": type(error).__name__, "message": str(error)})
        seeder.checkpoint()
        raise
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
