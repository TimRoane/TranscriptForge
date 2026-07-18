#!/usr/bin/env python3
"""Prepare frozen GPL570 cohort metadata and safely stage raw GEO CEL archives."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Final

MINIML: Final = "http://www.ncbi.nlm.nih.gov/geo/info/MINiML"
COHORTS: Final = {
    "GSE140494": {
        "role": "development",
        "response_tag": "pathological response",
        "expected_samples": 91,
        "expected_counts": {"pCR": 23, "nCR": 68},
        "raw_tar_sha256": "26230bbf9220631a9a7db915115c3d3db72a77b602c4795c03e6b6995a47b47b",
        "miniml_sha256": "15c1087806a7d6c5f07da278d415ecd16481b7a152ea469b4c49d03adf2a6f15",
    },
    "GSE32646": {
        "role": "external",
        "response_tag": "pathologic response pcr ncr",
        "expected_samples": 115,
        "expected_counts": {"pCR": 27, "nCR": 88},
        "raw_tar_sha256": "4e3545310427c9f497350f6b341f7568f9ef302b900c2cdb1c52da05cd2541fc",
        "miniml_sha256": "74238f8ba8165cecbc405f09b391338935a604f110ebb3034c98a34008f90e2a",
    },
}


@dataclass(frozen=True, slots=True)
class Sample:
    accession: str
    title: str
    cel_file: str
    response: str
    characteristics: dict[str, str]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_quick_miniml(accession: str, destination: Path) -> None:
    url = (
        "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?"
        f"acc={accession}&targ=gsm&form=xml&view=quick"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "TranscriptForge/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    if not payload.startswith(b"<?xml"):
        raise ValueError(f"GEO did not return MINiML XML for {accession}.")
    destination.write_bytes(payload)


def parse_samples(path: Path, response_tag: str) -> list[Sample]:
    root = ET.parse(path).getroot()
    namespace = {"m": MINIML}
    samples: list[Sample] = []
    for element in root.findall("m:Sample", namespace):
        accession = _text(element.find("m:Accession", namespace))
        title = _text(element.find("m:Title", namespace))
        characteristics = {
            item.attrib.get("tag", "").strip().lower(): _text(item)
            for item in element.findall(".//m:Characteristics", namespace)
        }
        supplementary = [
            _text(item)
            for item in element.findall("m:Supplementary-Data", namespace)
            if item.attrib.get("type", "").upper() == "CEL"
        ]
        if len(supplementary) != 1:
            raise ValueError(f"{accession} must declare exactly one raw CEL file.")
        cel_file = PurePath(supplementary[0]).name
        raw_response = characteristics.get(response_tag, "")
        if raw_response == "pCR":
            response = "pCR"
        elif raw_response in {"pPR", "pNC", "nCR"}:
            response = "nCR"
        else:
            raise ValueError(f"{accession} has unsupported pathological response '{raw_response}'.")
        samples.append(Sample(accession, title, cel_file, response, characteristics))
    return sorted(samples, key=lambda item: item.accession)


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return (element.text or "").strip()


def stage_cels(raw_tar: Path, samples: list[Sample], destination: Path) -> dict[str, str]:
    expected = {sample.cel_file for sample in samples}
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(raw_tar) as archive:
        members = archive.getmembers()
        unsafe = [member.name for member in members if PurePath(member.name).name != member.name]
        if unsafe:
            raise ValueError(f"Raw GEO archive contains unsafe member paths: {unsafe[:3]}.")
        names = {member.name for member in members if member.isfile()}
        missing = sorted(expected - names)
        unexpected = sorted(names - expected)
        if missing or unexpected:
            raise ValueError(
                f"Raw CEL archive mismatch: {len(missing)} missing and "
                f"{len(unexpected)} unexpected file(s)."
            )
        archive.extractall(destination, members=members, filter="data")
    return {name: sha256(destination / name) for name in sorted(expected)}


def patient_id(sample: Sample) -> str:
    if sample.title.startswith("BC_Patient"):
        return sample.title.removeprefix("BC_").split("_Genearray", maxsplit=1)[0]
    if "OU-" in sample.title:
        return sample.title.rsplit(" ", maxsplit=1)[-1]
    return sample.accession


def metadata_values(accession: str, sample: Sample, include_truth: bool) -> dict[str, str]:
    characteristics = sample.characteristics
    values = {
        "patient_id": patient_id(sample),
        "cohort": accession,
        "er_status": characteristics.get(
            "er status", characteristics.get("er status ihc", "")
        ),
        "pr_status": characteristics.get(
            "pr status", characteristics.get("pr status ihc", "")
        ),
        "her2_status": characteristics.get(
            "her2 status", characteristics.get("her2 status fish", "")
        ),
    }
    if include_truth:
        source_tag = str(COHORTS[accession]["response_tag"])
        values = {
            "response": sample.response,
            "source_pathological_response": characteristics[source_tag],
            **values,
        }
    return values


def write_metadata(path: Path, accession: str, samples: list[Sample], include_truth: bool) -> None:
    fields = [
        "sample_id",
        "cel_file",
        "patient_id",
        "cohort",
        "er_status",
        "pr_status",
        "her2_status",
    ]
    if include_truth:
        fields.insert(2, "response")
        fields.insert(3, "source_pathological_response")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for sample in samples:
            row = {
                "sample_id": sample.accession,
                "cel_file": sample.cel_file,
                **metadata_values(accession, sample, include_truth),
            }
            writer.writerow(row)


def write_truth(path: Path, samples: list[Sample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=False)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(("sample_id", "response"))
        writer.writerows((sample.accession, sample.response) for sample in samples)


def write_ingestion_manifest(
    path: Path,
    accession: str,
    samples: list[Sample],
    metadata: Path,
    cel_dir: Path,
    cel_checksums: dict[str, str],
    include_truth: bool,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    adapter_path = repository_root / "microarray/platforms/affymetrix_hg_u133_plus_2.json"
    adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    metadata_contract = {
        "dataset_file_id": f"{accession}-metadata",
        "role": "sample_metadata",
        "original_name": metadata.name,
        "storage_uri": f"local://classifier-external-validation/{accession}/{metadata.name}",
        "size_bytes": metadata.stat().st_size,
        "sha256": sha256(metadata),
    }
    payload = {
        "schema_version": "1.0.0",
        "dataset_id": f"classifier-external-validation-{accession}",
        "organism": "Homo sapiens",
        "source_kind": "affymetrix_cel",
        "platform": {
            "platform_id": adapter["platform_id"],
            "definition_sha256": sha256(adapter_path),
            "adapter_version": adapter["adapter_version"],
            "vendor": adapter["vendor"],
            "array_design": adapter["array_design"],
            "detected_chip_type": "HG-U133_Plus_2",
            "cel_format": "xda",
            "normalization": adapter["normalization"],
            "annotation": adapter["annotation"],
        },
        "aggregation_method": "median",
        "sample_metadata": metadata_contract,
        "sample_count": len(samples),
        "cel_file_count": len(samples),
        "samples": [
            {
                "sample_id": sample.accession,
                "cel_file": {
                    "dataset_file_id": f"{accession}-{sample.accession}",
                    "role": "cel_file",
                    "original_name": sample.cel_file,
                    "storage_uri": (
                        f"local://classifier-external-validation/{accession}/cel/"
                        f"{sample.cel_file}"
                    ),
                    "size_bytes": (cel_dir / sample.cel_file).stat().st_size,
                    "sha256": cel_checksums[sample.cel_file],
                },
                "metadata": metadata_values(accession, sample, include_truth),
            }
            for sample in samples
        ],
        "warnings": [],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run(accession: str, raw_tar: Path, output: Path) -> dict[str, object]:
    specification = COHORTS[accession]
    output.mkdir(parents=True, exist_ok=False)
    miniml = output / f"{accession}_quick_miniml.xml"
    download_quick_miniml(accession, miniml)
    observed_miniml_sha256 = sha256(miniml)
    if observed_miniml_sha256 != specification["miniml_sha256"]:
        raise ValueError(
            f"{accession} MINiML checksum changed: observed {observed_miniml_sha256}."
        )
    observed_raw_sha256 = sha256(raw_tar)
    if observed_raw_sha256 != specification["raw_tar_sha256"]:
        raise ValueError(
            f"{accession} raw CEL archive checksum changed: observed {observed_raw_sha256}."
        )
    samples = parse_samples(miniml, str(specification["response_tag"]))
    counts = {
        label: sum(sample.response == label for sample in samples)
        for label in ("pCR", "nCR")
    }
    if (
        len(samples) != specification["expected_samples"]
        or counts != specification["expected_counts"]
    ):
        raise ValueError(
            f"{accession} public metadata changed: observed {len(samples)} samples and {counts}."
        )
    cel_checksums = stage_cels(raw_tar, samples, output / "cel")
    include_truth = specification["role"] == "development"
    metadata = output / "sample_metadata.tsv"
    write_metadata(metadata, accession, samples, include_truth=include_truth)
    write_ingestion_manifest(
        output / "ingestion_manifest.json",
        accession,
        samples,
        metadata,
        output / "cel",
        cel_checksums,
        include_truth,
    )
    if not include_truth:
        write_truth(output / "sealed_truth" / "response.tsv", samples)
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "accession": accession,
        "role": specification["role"],
        "platform": "GPL570",
        "sample_count": len(samples),
        "class_counts": counts,
        "expression_bundle_contains_outcome": include_truth,
        "raw_tar": {
            "name": raw_tar.name,
            "size_bytes": raw_tar.stat().st_size,
            "sha256": observed_raw_sha256,
        },
        "miniml": {
            "name": miniml.name,
            "size_bytes": miniml.stat().st_size,
            "sha256": observed_miniml_sha256,
        },
        "metadata": {
            "name": metadata.name,
            "size_bytes": metadata.stat().st_size,
            "sha256": sha256(metadata),
        },
        "cel_files": cel_checksums,
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accession", choices=sorted(COHORTS), required=True)
    parser.add_argument("--raw-tar", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.accession, args.raw_tar.resolve(), args.output_dir.resolve())


if __name__ == "__main__":
    main()
