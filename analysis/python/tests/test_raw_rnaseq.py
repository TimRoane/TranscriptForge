"""Lane merging and raw RNA-seq Expression Bundle tests."""

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError
from jsonschema import Draft202012Validator
from transcriptforge_analysis.raw_bundle_cli import build_raw_bundle
from transcriptforge_analysis.raw_inputs import verify_inputs
from transcriptforge_analysis.raw_reference import _publish_s3_cache, _restore_s3_cache

ROOT = Path(__file__).resolve().parents[3]


class FakeReferenceS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.writes: list[str] = []

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        try:
            payload = self.objects[(bucket, key)]
        except KeyError as error:
            raise ClientError({"Error": {"Code": "404"}}, "GetObject") from error
        Path(destination).write_bytes(payload)

    def upload_file(self, source: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(source).read_bytes()
        self.writes.append(key)

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> dict[str, Any]:
        assert ContentType == "application/json"
        self.objects[(Bucket, Key)] = Body
        self.writes.append(Key)
        return {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reference_cache_fixture(root: Path) -> dict[str, Any]:
    (root / "assets").mkdir(parents=True)
    (root / "salmon_index").mkdir()
    (root / "assets/transcripts.fa.gz").write_bytes(b"transcripts")
    (root / "gentrome.fa").write_bytes(b"gentrome")
    (root / "decoys.txt").write_text("chr1\n", encoding="utf-8")
    (root / "tx2gene.tsv").write_text("transcript_id\tgene_id\ntx1\tg1\n")
    (root / "salmon_index/versionInfo.json").write_text("{}\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.1.0",
        "reference_id": "tiny-grch38",
        "definition_sha256": "a" * 64,
        "salmon_version": "1.11.4",
        "assets": [
            {
                "filename": "transcripts.fa.gz",
                "local_sha256": _sha256(root / "assets/transcripts.fa.gz"),
            }
        ],
        "gentrome_sha256": _sha256(root / "gentrome.fa"),
        "decoys_sha256": _sha256(root / "decoys.txt"),
        "tx2gene_sha256": _sha256(root / "tx2gene.tsv"),
        "index_files": {
            "versionInfo.json": _sha256(root / "salmon_index/versionInfo.json")
        },
    }
    (root / "reference_materialization.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def test_reference_cache_round_trips_through_immutable_s3_prefix(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    manifest = _reference_cache_fixture(source)
    client = FakeReferenceS3()

    _publish_s3_cache(
        "s3://fixture-bucket/references",
        "tiny-grch38",
        "a" * 64,
        source,
        manifest,
        s3_client=client,
    )

    assert client.writes[-1].endswith("/reference_materialization.json")
    restored = tmp_path / "restored"
    restored.mkdir()
    assert _restore_s3_cache(
        "s3://fixture-bucket/references",
        "tiny-grch38",
        "a" * 64,
        restored,
        s3_client=client,
    )
    assert (restored / "salmon_index/versionInfo.json").read_text() == "{}\n"
    assert (restored / "tx2gene.tsv").read_bytes() == (source / "tx2gene.tsv").read_bytes()


def test_verify_inputs_merges_frozen_lanes_by_logical_sample(tmp_path: Path) -> None:
    output = tmp_path / "verified"
    execution = verify_inputs(
        ROOT / "demo/raw_rnaseq/paired/ingestion_manifest.json",
        ROOT / "demo/raw_rnaseq/reference/reference.json",
        ROOT / "demo/raw_rnaseq/paired",
        output,
    )

    assert execution["lane_count"] == 8
    assert all(sample["lane_count"] == 2 for sample in execution["samples"])
    first = execution["samples"][0]
    with gzip.open(first["read1"], "rt", encoding="utf-8") as source:
        records = sum(1 for line in source if line.startswith("@"))
    assert records == 49
    assert [lane["lane_id"] for lane in first["lanes"]] == ["L001", "L002"]


def test_raw_bundle_preserves_transcript_abundance_and_qc(tmp_path: Path) -> None:
    execution = tmp_path / "execution.json"
    execution.write_text(
        json.dumps(
            {
                "dataset_id": "raw-dataset",
                "organism": "Homo sapiens",
                "genome_build": "GRCh38.p14",
                "annotation_release": "GENCODE 50",
            }
        ),
        encoding="utf-8",
    )
    counts = tmp_path / "counts.tsv"
    counts.write_text(
        "feature_id\tsample_A\tsample_B\n"
        "ENSG00000141510\t10\t4\nENSG00000146648\t2\t8\n",
        encoding="utf-8",
    )
    tpm = tmp_path / "tpm.tsv"
    tpm.write_text(
        "feature_id\tsample_A\tsample_B\n"
        "ENSG00000141510\t80\t30\nENSG00000146648\t20\t70\n",
        encoding="utf-8",
    )
    transcript_tpm = tmp_path / "transcript.tsv"
    transcript_tpm.write_text(
        "feature_id\tsample_A\tsample_B\nENST000001\t80\t30\nENST000002\t20\t70\n",
        encoding="utf-8",
    )
    metadata = tmp_path / "metadata.tsv"
    metadata.write_text("sample_id\tcondition\nsample_A\tcontrol\nsample_B\ttreated\n")
    qc_metrics = tmp_path / "raw_qc.tsv"
    qc_metrics.write_text("sample_id\tmitochondrial_percent\nsample_A\t1\nsample_B\t2\n")
    qc_summary = tmp_path / "raw_qc.json"
    qc_summary.write_text(json.dumps({"status": "REVIEW"}), encoding="utf-8")
    output = tmp_path / "output"

    build_raw_bundle(
        execution,
        counts,
        tpm,
        transcript_tpm,
        qc_metrics,
        qc_summary,
        metadata,
        output,
        "prepared-raw-v1",
        1,
    )

    manifest = json.loads(
        (output / "expression_bundle/bundle_manifest.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        (ROOT / "schemas/expression_bundle.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(manifest)
    assert [assay["name"] for assay in manifest["assays"]] == [
        "raw_counts",
        "log_expression",
        "tpm",
        "transcript_abundance",
    ]
    assert manifest["qc"]["status"] == "REVIEW"
    summary = json.loads((output / "bundle_summary.json").read_text(encoding="utf-8"))
    assert summary["transcript_abundance_available"] is True
    assert "transcript_abundance" not in summary["value_types_available"]
