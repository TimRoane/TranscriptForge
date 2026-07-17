#!/usr/bin/env python3
"""Assert the public paired microarray bundle runs through limma coherently."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: check_limma_acceptance.py RESULTS_DIR")
    root = Path(sys.argv[1])
    diagnostics = json.loads((root / "method_diagnostics.json").read_text())
    contrast = json.loads((root / "contrast.json").read_text())
    manifest = json.loads((root / "result_manifest.json").read_text())
    with (root / "differential_expression.tsv").open(newline="") as handle:
        results = list(csv.DictReader(handle, delimiter="\t"))
    with (root / "normalized_expression.tsv").open(newline="") as handle:
        profiles = csv.reader(handle, delimiter="\t")
        profile_header = next(profiles)
        profile_rows = sum(1 for _ in profiles)

    require(diagnostics["method"] == "limma", "Public microarray acceptance did not use limma.")
    require(diagnostics["assay"] == "log_expression", "limma did not use log_expression.")
    require(diagnostics["formula"] == "~ donor + zone", "The paired donor design was not fitted.")
    require(diagnostics["sample_count"] == 8, "The paired design did not retain all eight arrays.")
    require(diagnostics["design_rank"] == 5, "The paired design matrix is not full rank 5.")
    require(diagnostics["features_tested"] >= 20_000, "Too few mapped genes reached limma.")
    require(
        contrast["coefficient_definition"] == "superficial minus deep",
        "Contrast direction drifted.",
    )
    require(
        len(contrast["design_coefficient_weights"]) == 5,
        "Contrast weights do not match the design.",
    )
    require(
        len(results) == diagnostics["features_tested"],
        "Complete result row count is inconsistent.",
    )
    require(profile_rows == len(results), "Normalized profiles are incomplete.")
    require(len(profile_header) == 9, "Normalized profiles do not contain all eight arrays.")
    require(
        all(row["method"] == "limma" for row in results),
        "Result method labels are inconsistent.",
    )
    require(
        all(row["contrast"] == "superficial versus deep within zone" for row in results),
        "Result contrast labels are inconsistent.",
    )
    require(manifest["analysis_type"] == "differential_expression", "Result Manifest type drifted.")
    for name in (
        "significant_results.tsv",
        "design_matrix.tsv",
        "volcano_plot.json",
        "ma_plot.json",
        "p_value_distribution.json",
        "expression_heatmap.json",
        "session_info.txt",
        "report.qmd",
    ):
        require((root / name).is_file(), f"limma output is missing {name}.")
    print(
        "PASS paired public microarray limma: "
        f"samples=8 tested={len(results)} significant={diagnostics['significant_features']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
