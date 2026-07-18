"""Prospective GEO classifier-cohort preparation tests."""

import io
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from demo.classifier_external_validation.prepare_geo_cohort import parse_samples, stage_cels

NS = "http://www.ncbi.nlm.nih.gov/geo/info/MINiML"


def test_miniml_response_mapping_and_safe_cel_staging(tmp_path: Path) -> None:
    root = ET.Element(f"{{{NS}}}MINiML")
    for accession, response in (("GSM2", "pPR"), ("GSM1", "pCR")):
        sample = ET.SubElement(root, f"{{{NS}}}Sample")
        ET.SubElement(sample, f"{{{NS}}}Title").text = f"BC_Patient{accession}_Genearray1"
        ET.SubElement(sample, f"{{{NS}}}Accession").text = accession
        channel = ET.SubElement(sample, f"{{{NS}}}Channel")
        characteristic = ET.SubElement(
            channel, f"{{{NS}}}Characteristics", {"tag": "pathological response"}
        )
        characteristic.text = response
        supplementary = ET.SubElement(
            sample, f"{{{NS}}}Supplementary-Data", {"type": "CEL"}
        )
        supplementary.text = f"ftp://example.test/{accession}.CEL.gz"
    miniml = tmp_path / "metadata.xml"
    ET.ElementTree(root).write(miniml, encoding="utf-8", xml_declaration=True)
    samples = parse_samples(miniml, "pathological response")
    assert [(sample.accession, sample.response) for sample in samples] == [
        ("GSM1", "pCR"),
        ("GSM2", "nCR"),
    ]

    archive_path = tmp_path / "raw.tar"
    with tarfile.open(archive_path, "w") as archive:
        for sample in samples:
            payload = sample.accession.encode()
            member = tarfile.TarInfo(sample.cel_file)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    checksums = stage_cels(archive_path, samples, tmp_path / "cel")
    assert set(checksums) == {"GSM1.CEL.gz", "GSM2.CEL.gz"}


def test_cel_staging_rejects_archive_paths(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.tar"
    with tarfile.open(archive_path, "w") as archive:
        member = tarfile.TarInfo("../GSM1.CEL.gz")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="unsafe member paths"):
        stage_cels(archive_path, [], tmp_path / "cel")
