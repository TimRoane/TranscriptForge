"""Generate the small, versioned GMT collections used by demos and acceptance tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def synthetic_id(number: int) -> str:
    return f"ENSG9{number:010d}"


def fixture_ids(prefix: str, count: int) -> list[str]:
    return [f"gene_{prefix}_{number:02d}" for number in range(1, count + 1)]


def write_collection(
    collection_id: str,
    *,
    name: str,
    version: str,
    namespace: str,
    source: str,
    license_name: str,
    sets: list[tuple[str, str, list[str]]],
) -> None:
    gmt_name = f"{collection_id}.gmt"
    gmt_path = ROOT / gmt_name
    lines = ["\t".join((set_id, description, *members)) for set_id, description, members in sets]
    gmt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    digest = hashlib.sha256(gmt_path.read_bytes()).hexdigest()
    metadata = {
        "schema_version": "1.0.0",
        "collection_id": collection_id,
        "name": name,
        "version": version,
        "identifier_namespace": namespace,
        "source": source,
        "license": license_name,
        "gmt_file": gmt_name,
        "gmt_sha256": digest,
        "set_count": len(sets),
    }
    (ROOT / f"{collection_id}.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    write_collection(
        "transcriptforge_demo_effects",
        name="TranscriptForge simulated-effect controls",
        version="1.0.0",
        namespace="synthetic_ensembl_like_feature_id",
        source="TranscriptForge deterministic 72-sample demonstration ground truth",
        license_name="PolyForm-Noncommercial-1.0.0",
        sets=[
            (
                "TF_DEMO_TREATMENT_UP",
                "Simulated treatment-positive control",
                [synthetic_id(i) for i in range(1, 151)],
            ),
            (
                "TF_DEMO_GENOTYPE_UP",
                "Simulated genotype-positive control",
                [synthetic_id(i) for i in range(151, 271)],
            ),
            (
                "TF_DEMO_INTERACTION_UP",
                "Simulated genotype-treatment interaction control",
                [synthetic_id(i) for i in range(271, 351)],
            ),
            (
                "TF_DEMO_BATCH",
                "Simulated batch-effect control",
                [synthetic_id(i) for i in range(351, 431)],
            ),
            (
                "TF_DEMO_SEX",
                "Simulated sex-effect control",
                [synthetic_id(i) for i in range(431, 471)],
            ),
            (
                "TF_DEMO_TREATMENT_DOWN",
                "Simulated treatment-negative control",
                [synthetic_id(i) for i in range(471, 571)],
            ),
            (
                "TF_DEMO_NULL_CONTROL",
                "Simulated null/noise control",
                [synthetic_id(i) for i in range(571, 771)],
            ),
        ],
    )
    write_collection(
        "transcriptforge_acceptance_effects",
        name="TranscriptForge R acceptance controls",
        version="1.0.0",
        namespace="acceptance_fixture_feature_id",
        source="TranscriptForge deterministic R differential-expression acceptance fixture",
        license_name="PolyForm-Noncommercial-1.0.0",
        sets=[
            ("TF_ACCEPTANCE_UP", "Known positive fixture effects", fixture_ids("up", 15)),
            ("TF_ACCEPTANCE_DOWN", "Known negative fixture effects", fixture_ids("down", 15)),
            ("TF_ACCEPTANCE_NULL", "Known null fixture controls", fixture_ids("null", 30)),
        ],
    )


if __name__ == "__main__":
    main()
