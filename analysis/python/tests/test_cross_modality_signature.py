"""Cross-modality signature acceptance contract tests."""

import importlib.util
import json
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[3]
SPEC = importlib.util.spec_from_file_location(
    "cross_modality_signature_acceptance",
    ROOT / "demo/cross_modality_signature/run_acceptance.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load the cross-modality acceptance runner.")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
run_acceptance: Callable[[Path], dict[str, Any]] = MODULE.run_acceptance


def test_same_frozen_signature_passes_rnaseq_and_microarray_acceptance(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    result = run_acceptance(first_dir)
    repeated = run_acceptance(second_dir)

    assert result == repeated
    assert result["passed"] is True
    assert result["interpretation_boundary"]["raw_score_scale_comparable"] is False
    assert "must not be compared across RNA-seq" in result["interpretation_boundary"]["warning"]
    assert result["concordance"] == {
        "same_signature_sha256": True,
        "direction_concordant": True,
        "both_meet_mapping_threshold": True,
        "both_meet_fdr_threshold": True,
        "both_meet_auc_threshold": True,
        "raw_scales_distinct": True,
    }
    cohorts = {item["modality"]: item for item in result["cohorts"]}
    assert set(cohorts) == {"bulk_rnaseq", "microarray"}
    assert cohorts["bulk_rnaseq"]["signature_definition_sha256"] == (
        cohorts["microarray"]["signature_definition_sha256"]
    )
    assert cohorts["bulk_rnaseq"]["mapping_report_sha256"] != (
        cohorts["microarray"]["mapping_report_sha256"]
    )
    assert all(item["auc"] == 1 for item in cohorts.values())
    assert first_dir.joinpath("cross_modality_acceptance.json").read_bytes() == (
        second_dir / "cross_modality_acceptance.json"
    ).read_bytes()
    for modality in cohorts:
        score_summary = json.loads(
            (first_dir / modality / "scores/signature_scores.json").read_text()
        )
        assert "must not be compared across RNA-seq" in score_summary["warnings"][0]

    with tarfile.open(first_dir / "microarray/expression_bundle.tar.gz") as archive:
        source = archive.extractfile("expression_bundle/bundle_manifest.json")
        assert source is not None
        microarray_manifest = json.load(source)
    assert microarray_manifest["microarray"]["normalization_method"] == "rma"

    with tarfile.open(first_dir / "bulk_rnaseq/expression_bundle.tar.gz") as archive:
        source = archive.extractfile("expression_bundle/bundle_manifest.json")
        assert source is not None
        rnaseq_manifest = json.load(source)
    assert [item["name"] for item in rnaseq_manifest["assays"]] == [
        "raw_counts",
        "log_expression",
    ]
