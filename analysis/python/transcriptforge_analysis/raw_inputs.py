"""Verify a frozen raw RNA-seq ingestion manifest against staged read bytes."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path, PurePath
from typing import Any

from transcriptforge_analysis.matrix_validation import write_json_atomic


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_path(reads_dir: Path, contract: dict[str, Any]) -> Path:
    name = str(contract["original_name"])
    if PurePath(name).name != name or "/" in name or "\\" in name:
        raise RuntimeError(f"Frozen FASTQ name is unsafe: {name}.")
    path = reads_dir / name
    if not path.is_file():
        raise RuntimeError(f"Frozen FASTQ is missing from staged inputs: {name}.")
    if path.stat().st_size != int(contract["size_bytes"]):
        raise RuntimeError(f"Staged FASTQ size drift for {name}.")
    observed = _sha256(path)
    if observed != contract["sha256"]:
        raise RuntimeError(f"Staged FASTQ checksum drift for {name}.")
    return path.resolve()


def _library_type(layout: str, strandedness: str) -> str:
    if layout == "paired_end":
        return {"auto": "A", "unstranded": "IU", "forward": "ISF", "reverse": "ISR"}[
            strandedness
        ]
    return {"auto": "A", "unstranded": "U", "forward": "SF", "reverse": "SR"}[
        strandedness
    ]


def _merge_reads(paths: list[Path], target: Path) -> None:
    """Normalize one or more FASTQ lanes into one deterministic gzip stream."""
    with target.open("wb") as raw_output, gzip.GzipFile(
        fileobj=raw_output, mode="wb", filename="", mtime=0
    ) as destination:
        for path in paths:
            if path.name.lower().endswith(".gz"):
                with gzip.open(path, "rb") as source:
                    shutil.copyfileobj(source, destination)
            else:
                with path.open("rb") as source:
                    shutil.copyfileobj(source, destination)


def verify_inputs(
    ingestion_path: Path, definition_path: Path, reads_dir: Path, output_dir: Path
) -> dict[str, Any]:
    ingestion = dict(json.loads(ingestion_path.read_text(encoding="utf-8")))
    definition_bytes = definition_path.read_bytes()
    definition = dict(json.loads(definition_bytes))
    definition_sha = hashlib.sha256(definition_bytes).hexdigest()
    if ingestion["reference"]["definition_sha256"] != definition_sha:
        raise RuntimeError("Reference definition drifted after raw RNA-seq ingestion.")
    if ingestion["reference"]["reference_id"] != definition["reference_id"]:
        raise RuntimeError("Ingestion and reference definition IDs disagree.")
    if ingestion["reference"]["salmon_version"] != definition["salmon"]["version"]:
        raise RuntimeError("Ingestion and reference Salmon versions disagree.")

    seen: set[str] = set()
    samples: list[dict[str, Any]] = []
    metadata_columns: list[str] = []
    merged_dir = output_dir / "merged_reads"
    merged_dir.mkdir(parents=True, exist_ok=True)
    observed_lane_count = 0
    for sample in ingestion["samples"]:
        sample_id = str(sample["sample_id"])
        if sample_id in seen:
            raise RuntimeError(f"Frozen ingestion contains duplicate sample {sample_id}.")
        seen.add(sample_id)
        for column in sample["metadata"]:
            if column not in metadata_columns:
                metadata_columns.append(column)
        lanes = sample["lanes"]
        if not lanes:
            raise RuntimeError(f"Frozen ingestion has no lanes for sample {sample_id}.")
        lane_ids: set[str] = set()
        read1_lanes: list[Path] = []
        read2_lanes: list[Path] = []
        lane_records: list[dict[str, Any]] = []
        for lane in lanes:
            lane_id = str(lane["lane_id"])
            if lane_id in lane_ids:
                raise RuntimeError(f"Frozen ingestion repeats lane {lane_id} for {sample_id}.")
            lane_ids.add(lane_id)
            read1 = _read_path(reads_dir, lane["read1"])
            read2 = _read_path(reads_dir, lane["read2"]) if lane["read2"] else None
            if (read2 is not None) != (ingestion["library_layout"] == "paired_end"):
                raise RuntimeError(f"Frozen lane layout disagrees for {sample_id}/{lane_id}.")
            read1_lanes.append(read1)
            if read2 is not None:
                read2_lanes.append(read2)
            lane_records.append(
                {
                    "lane_id": lane_id,
                    "read1": str(read1),
                    "read2": str(read2) if read2 else None,
                }
            )
        merged_read1 = merged_dir / f"{sample_id}.merged_R1.fastq.gz"
        _merge_reads(read1_lanes, merged_read1)
        merged_read2 = merged_dir / f"{sample_id}.merged_R2.fastq.gz"
        if read2_lanes:
            _merge_reads(read2_lanes, merged_read2)
        observed_lane_count += len(lanes)
        samples.append(
            {
                "sample_id": sample_id,
                "lane_count": len(lanes),
                "lanes": lane_records,
                "read1": str(merged_read1.resolve()),
                "read2": str(merged_read2.resolve()) if read2_lanes else None,
                "metadata": sample["metadata"],
            }
        )
    if len(samples) != int(ingestion["sample_count"]):
        raise RuntimeError("Frozen sample count does not match the ingestion rows.")
    if observed_lane_count != int(ingestion["lane_count"]):
        raise RuntimeError("Frozen lane count does not match the ingestion rows.")

    metadata_path = output_dir / "sample_metadata.tsv"
    with metadata_path.open("w", encoding="utf-8", newline="") as destination:
        destination.write("sample_id")
        for column in metadata_columns:
            destination.write(f"\t{column}")
        destination.write("\n")
        for sample in samples:
            destination.write(sample["sample_id"])
            for column in metadata_columns:
                destination.write(f"\t{sample['metadata'].get(column, '')}")
            destination.write("\n")
    execution = {
        "schema_version": "1.0.0",
        "dataset_id": ingestion["dataset_id"],
        "organism": ingestion["organism"],
        "genome_build": ingestion["genome_build"],
        "annotation_release": ingestion["reference"]["annotation_release"],
        "layout": ingestion["library_layout"],
        "strandedness": ingestion["strandedness"],
        "lane_count": observed_lane_count,
        "salmon_library_type": _library_type(
            ingestion["library_layout"], ingestion["strandedness"]
        ),
        "samples": samples,
    }
    write_json_atomic(output_dir / "execution_manifest.json", execution)
    return execution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingestion", required=True, type=Path)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--reads-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    verify_inputs(args.ingestion, args.definition, args.reads_dir, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
