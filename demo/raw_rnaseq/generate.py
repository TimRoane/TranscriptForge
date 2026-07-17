"""Generate deterministic, valid tiny RNA-seq reads and a checksum-pinned reference."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import random
from pathlib import Path

ROOT = Path(__file__).parent
REFERENCE = ROOT / "reference"
PAIRED = ROOT / "paired"
SINGLE = ROOT / "single"
SALMON_VERSION = "1.11.4"


def sequence(seed: int, length: int) -> str:
    generator = random.Random(seed)
    return "".join(generator.choice("ACGT") for _ in range(length))


TRANSCRIPTS = {
    "ENSTFIX000001": ("ENSGFIX000001", sequence(101, 360)),
    "ENSTFIX000002": ("ENSGFIX000002", sequence(202, 360)),
    "ENSTFIX000003": ("ENSGFIX000003", sequence(303, 360)),
    "ENSTFIX000004": ("ENSGFIX000004", sequence(404, 360)),
}


def gzip_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as destination:
        destination.write(text.encode())
    return buffer.getvalue()


def write_gzip(path: Path, text: str) -> None:
    path.write_bytes(gzip_bytes(text))


def reverse_complement(value: str) -> str:
    return value.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def fastq_record(name: str, value: str) -> str:
    return f"@{name}\n{value}\n+\n{'I' * len(value)}\n"


def reads_for_sample(
    sample: str, counts: tuple[int, int, int, int], paired: bool
) -> tuple[str, str]:
    read1: list[str] = []
    read2: list[str] = []
    read_number = 0
    for transcript_index, ((transcript_id, (_, value)), count) in enumerate(
        zip(TRANSCRIPTS.items(), counts, strict=True)
    ):
        for within_gene in range(count):
            read_number += 1
            offset = (within_gene * 7 + transcript_index * 11) % 120
            fragment = value[offset : offset + 210]
            name = f"{sample}:{read_number}:{transcript_id}"
            read1.append(fastq_record(f"{name}/1", fragment[:75]))
            if paired:
                read2.append(fastq_record(f"{name}/2", reverse_complement(fragment[135:210])))
    return "".join(read1), "".join(read2)


def write_reference() -> None:
    REFERENCE.mkdir(parents=True, exist_ok=True)
    transcriptome = "".join(
        f">{transcript_id}\n{value}\n"
        for transcript_id, (_, value) in TRANSCRIPTS.items()
    )
    genome = f">chrM\n{sequence(998, 600)}\n>chr1\n{sequence(999, 1800)}\n"
    gtf_lines = ["##description: TranscriptForge deterministic tiny fixture"]
    for index, (transcript_id, (gene_id, _)) in enumerate(TRANSCRIPTS.items(), start=1):
        seqname = "chrM" if index == 1 else "chr1"
        start = 1 if index == 1 else (index - 2) * 400 + 1
        end = start + 359
        gene_type = "rRNA" if index == 2 else "protein_coding"
        attributes = (
            f'gene_id "{gene_id}"; transcript_id "{transcript_id}"; '
            f'gene_name "FIX{index}"; gene_type "{gene_type}";'
        )
        gtf_lines.append(
            f"{seqname}\tTranscriptForge\ttranscript\t{start}\t{end}\t.\t+\t.\t{attributes}"
        )
    assets = {
        "tiny.transcripts.fa.gz": gzip_bytes(transcriptome),
        "tiny.genome.fa.gz": gzip_bytes(genome),
        "tiny.annotation.gtf.gz": gzip_bytes("\n".join(gtf_lines) + "\n"),
    }
    for name, payload in assets.items():
        (REFERENCE / name).write_bytes(payload)
    roles = {
        "tiny.transcripts.fa.gz": "transcriptome_fasta",
        "tiny.genome.fa.gz": "primary_assembly_genome",
        "tiny.annotation.gtf.gz": "annotation_gtf",
    }
    definition = {
        "schema_version": "1.0.0",
        "reference_id": "transcriptforge_tiny_grch38_salmon_1_11_4",
        "name": "TranscriptForge deterministic tiny GRCh38 Salmon fixture",
        "organism": "Homo sapiens",
        "genome_build": "GRCh38.p14",
        "annotation_provider": "GENCODE",
        "annotation_release": 50,
        "ensembl_release": 116,
        "source_page": "https://transcriptforge.dev/fixtures/tiny-reference",
        "terms_url": "https://transcriptforge.dev/fixtures/license",
        "salmon": {
            "version": SALMON_VERSION,
            "index_strategy": "selective_alignment_full_genome_decoy",
            "kmer_length": 15,
            "decoy_source": "primary_assembly_genome",
        },
        "assets": [
            {
                "role": roles[name],
                "filename": name,
                "url": f"https://transcriptforge.dev/fixtures/{name}",
                "upstream_checksum": {
                    "algorithm": "md5",
                    "value": hashlib.md5(payload).hexdigest(),
                    "manifest_url": "https://transcriptforge.dev/fixtures/MD5SUMS",
                },
            }
            for name, payload in assets.items()
        ],
    }
    (REFERENCE / "reference.json").write_text(
        json.dumps(definition, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_study(directory: Path, paired: bool) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for existing in directory.glob("*.fastq.gz"):
        existing.unlink()
    design = (
        ("control_1", "control", "1", (24, 5, 12, 8)),
        ("control_2", "control", "2", (22, 6, 13, 8)),
        ("treated_1", "treated", "1", (5, 24, 12, 8)),
        ("treated_2", "treated", "2", (6, 22, 13, 8)),
    )
    rows = ["sample_id\tlane_id\tread1\tread2\tcondition\treplicate\tbatch"]
    sample_lanes: dict[str, list[tuple[str, Path, Path | None]]] = {}
    for sample, condition, replicate, counts in design:
        lane_counts = (
            [tuple(value // 2 for value in counts), tuple(value - value // 2 for value in counts)]
            if paired
            else [counts]
        )
        sample_lanes[sample] = []
        for lane_index, counts_for_lane in enumerate(lane_counts, start=1):
            lane_id = f"L{lane_index:03d}"
            read1, read2 = reads_for_sample(
                f"{sample}:{lane_id}", counts_for_lane, paired
            )
            read1_name = f"{sample}_{lane_id}_R1.fastq.gz"
            read1_path = directory / read1_name
            write_gzip(read1_path, read1)
            read2_name = f"{sample}_{lane_id}_R2.fastq.gz" if paired else ""
            read2_path = directory / read2_name if paired else None
            if read2_path is not None:
                write_gzip(read2_path, read2)
            sample_lanes[sample].append((lane_id, read1_path, read2_path))
            rows.append(
                f"{sample}\t{lane_id}\t{read1_name}\t{read2_name}\t"
                f"{condition}\t{replicate}\tbatch_A"
            )
    (directory / "sample_sheet.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    definition_sha256 = hashlib.sha256((REFERENCE / "reference.json").read_bytes()).hexdigest()
    sample_sheet = directory / "sample_sheet.tsv"

    def file_contract(path: Path, role: str) -> dict[str, object]:
        return {
            "dataset_file_id": f"fixture-{directory.name}-{path.name}",
            "role": role,
            "original_name": path.name,
            "storage_uri": f"fixture://{directory.name}/{path.name}",
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    samples = []
    for sample, condition, replicate, _ in design:
        samples.append(
            {
                "sample_id": sample,
                "lanes": [
                    {
                        "lane_id": lane_id,
                        "read1": file_contract(read1, "fastq_r1"),
                        "read2": file_contract(read2, "fastq_r2") if read2 else None,
                    }
                    for lane_id, read1, read2 in sample_lanes[sample]
                ],
                "metadata": {
                    "condition": condition,
                    "replicate": replicate,
                    "batch": "batch_A",
                },
            }
        )
    ingestion = {
        "schema_version": "1.1.0",
        "dataset_id": f"fixture-{directory.name}",
        "organism": "Homo sapiens",
        "genome_build": "GRCh38.p14",
        "source_kind": "fastq",
        "reference": {
            "reference_id": "transcriptforge_tiny_grch38_salmon_1_11_4",
            "definition_sha256": definition_sha256,
            "name": "TranscriptForge deterministic tiny GRCh38 Salmon fixture",
            "annotation_release": "GENCODE 50",
            "salmon_version": SALMON_VERSION,
        },
        "sample_sheet": file_contract(sample_sheet, "sample_sheet"),
        "library_layout": "paired_end" if paired else "single_end",
        "strandedness": "unstranded",
        "sample_count": len(samples),
        "lane_count": sum(len(sample["lanes"]) for sample in samples),
        "read_file_count": sum(
            2 if lane["read2"] else 1
            for sample in samples
            for lane in sample["lanes"]
        ),
        "samples": samples,
        "warnings": [],
    }
    (directory / "ingestion_manifest.json").write_text(
        json.dumps(ingestion, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    write_reference()
    write_study(PAIRED, paired=True)
    write_study(SINGLE, paired=False)


if __name__ == "__main__":
    main()
