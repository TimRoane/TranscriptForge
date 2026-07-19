"""Run or verify every deterministic assay-development validation template locally."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from demo.assay_development.generate_input_limit_fixture import generate as input_limit
from demo.assay_development.generate_multifactor_fixture import generate as multifactor
from demo.assay_development.generate_paired_bridge_fixture import generate as paired_bridge
from demo.assay_development.generate_paired_condition_fixture import generate as paired_condition
from demo.assay_development.generate_precision_fixture import generate as precision
from demo.assay_development.generate_robustness_fixture import generate as robustness
from demo.assay_development.generate_technical_feasibility_fixture import (
    generate as technical_feasibility,
)

Generator = Callable[[Path], dict[str, str]]


@dataclass(frozen=True, slots=True)
class Template:
    key: str
    domain: str
    generate: Generator


TEMPLATES = (
    Template("technical_feasibility", "experiment", technical_feasibility),
    Template("paired_condition", "experiment", paired_condition),
    Template("multifactor_optimization", "experiment", multifactor),
    Template("precision_reproducibility", "study", precision),
    Template("input_degradation_limit", "study", input_limit),
    Template("paired_bridging", "study", paired_bridge),
    Template("robustness_interference", "study", robustness),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_path(output: Path, domain: str) -> Path:
    if domain == "experiment":
        return output / "experiment/results/development_evidence_bundle/manifest.json"
    return output / "study/results/validation_bundle/manifest.json"


def _archive_path(output: Path, domain: str) -> Path:
    if domain == "experiment":
        return output / "experiment/results/development_evidence_bundle.tar.gz"
    return output / "study/results/validation_bundle.tar.gz"


def _run(template: Template, root: Path, nextflow: str) -> dict[str, object]:
    inputs = template.generate(root / "inputs" / template.key)
    output = root / "results" / template.key
    manifest_path = _manifest_path(output, template.domain)
    cached = manifest_path.is_file()
    started = time.monotonic()
    if not cached:
        command = [
            nextflow,
            "run",
            "pipelines/main.nf",
            "-entry",
            "RUN_ASSAY_EXPERIMENT" if template.domain == "experiment" else "RUN_ASSAY_STUDY",
            "-profile",
            "test",
        ]
        if template.domain == "experiment":
            command.extend(
                [
                    "--experiment_spec",
                    inputs["experiment_spec"],
                    "--experiment_assignments",
                    inputs["experiment_assignments"],
                    "--expression_bundle",
                    inputs["expression_bundle"],
                ]
            )
        else:
            command.extend(
                [
                    "--study_spec",
                    inputs["study_spec"],
                    "--study_assignments",
                    inputs["study_assignments"],
                    "--expression_bundle",
                    inputs["expression_bundle"],
                    "--model",
                    inputs["model"],
                    "--model_manifest",
                    inputs["model_manifest"],
                ]
            )
        command.extend(["--analysis_python", sys.executable, "--outdir", str(output)])
        subprocess.run(command, check=True)
    if not manifest_path.is_file():
        raise RuntimeError(f"{template.key} did not publish its required manifest.")
    archive = _archive_path(output, template.domain)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "template": template.key,
        "domain": template.domain,
        "status": payload.get("overall_status", "EVIDENCE_GENERATED"),
        "scientist_decision_required": payload.get("scientist_decision_required"),
        "model_retrained": payload.get("model_retrained"),
        "cached": cached,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "manifest": str(manifest_path),
        "manifest_sha256": _sha(manifest_path),
        "archive": str(archive),
        "archive_sha256": _sha(archive),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".transcriptforge-demo/assay_development/portfolio"),
    )
    parser.add_argument("--nextflow", default="nextflow")
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    evidence = [_run(item, arguments.output_dir, arguments.nextflow) for item in TEMPLATES]
    summary = {
        "schema_version": "1.0.0",
        "execution_profile": "local-test",
        "python_executable": sys.executable,
        "template_count": len(evidence),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "templates": evidence,
        "scientific_boundary": (
            "Deterministic software evidence only; advancement and scientific interpretation "
            "remain human decisions."
        ),
    }
    summary_path = arguments.output_dir / "portfolio_execution_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({**summary, "summary_path": str(summary_path)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
