"""Checksum-verified, version-locked Salmon reference materialization."""

from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import IO, Any, cast
from urllib.parse import urlparse

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from transcriptforge_analysis.matrix_validation import write_json_atomic

ASSET_ROLES = {"transcriptome_fasta", "primary_assembly_genome", "annotation_gtf"}
ATTRIBUTE = re.compile(r'(\w+)\s+"([^"]+)"')
MATERIALIZATION_SCHEMA_VERSION = "1.1.0"


def _digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _copy_stream(source: IO[bytes], destination: IO[bytes]) -> None:
    shutil.copyfileobj(source, destination, length=1024 * 1024)


def _link_or_copy(source: str, destination: str) -> str:
    """Hard-link cache bytes when possible and copy across filesystem boundaries."""
    try:
        os.link(source, destination)
        return destination
    except OSError:
        return shutil.copy2(source, destination)


def _materialize_asset(asset: dict[str, Any], asset_dir: Path | None, target: Path) -> None:
    local = asset_dir / str(asset["filename"]) if asset_dir is not None else None
    temporary = target.with_name(f".{target.name}.partial")
    temporary.unlink(missing_ok=True)
    try:
        if local is not None:
            if not local.is_file():
                raise RuntimeError(f"Reference fixture asset is missing: {local}.")
            with local.open("rb") as source, temporary.open("wb") as destination:
                _copy_stream(source, destination)
        else:
            request = urllib.request.Request(
                str(asset["url"]), headers={"User-Agent": "TranscriptForge/0.1.0"}
            )
            with urllib.request.urlopen(request, timeout=120) as source, temporary.open(
                "wb"
            ) as destination:
                _copy_stream(source, destination)
        expected = str(asset["upstream_checksum"]["value"])
        observed = _digest(temporary, "md5")
        if observed != expected:
            raise RuntimeError(
                f"Upstream MD5 mismatch for {asset['filename']}: expected {expected}, "
                f"observed {observed}."
            )
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _open_maybe_gzip(path: Path) -> IO[bytes]:
    if path.suffix == ".gz":
        return cast(IO[bytes], gzip.open(path, "rb"))
    return path.open("rb")


def _fasta_headers(path: Path) -> list[str]:
    headers: list[str] = []
    with _open_maybe_gzip(path) as source:
        for raw in source:
            if raw.startswith(b">"):
                headers.append(raw[1:].split(maxsplit=1)[0].decode("utf-8"))
    if not headers:
        raise RuntimeError(f"Reference FASTA has no records: {path.name}.")
    return headers


def _write_gentrome(transcriptome: Path, genome: Path, target: Path) -> None:
    with target.open("wb") as destination:
        for source_path in (transcriptome, genome):
            with _open_maybe_gzip(source_path) as source:
                _copy_stream(source, destination)


def _write_tx2gene(gtf: Path, target: Path) -> int:
    records: dict[str, tuple[str, str, str, str]] = {}
    with _open_maybe_gzip(gtf) as binary:
        for raw in binary:
            if raw.startswith(b"#"):
                continue
            fields = raw.decode("utf-8").rstrip("\n").split("\t")
            if len(fields) != 9 or fields[2] not in {"transcript", "exon"}:
                continue
            attributes: dict[str, str] = dict(ATTRIBUTE.findall(fields[8]))
            transcript_id = attributes.get("transcript_id")
            gene_id = attributes.get("gene_id")
            if transcript_id and gene_id:
                record = (
                    gene_id,
                    attributes.get("gene_name", ""),
                    attributes.get("gene_type", attributes.get("gene_biotype", "")),
                    fields[0],
                )
                existing = records.get(transcript_id)
                if existing is not None and existing != record:
                    raise RuntimeError(
                        f"Annotation GTF disagrees for transcript {transcript_id}."
                    )
                records[transcript_id] = record
    if not records:
        raise RuntimeError("Annotation GTF did not contain transcript_id/gene_id mappings.")
    with target.open("w", encoding="utf-8", newline="") as destination:
        destination.write("transcript_id\tgene_id\tgene_name\tgene_type\tseqname\n")
        for transcript_id, record in sorted(records.items()):
            destination.write(f"{transcript_id}\t" + "\t".join(record) + "\n")
    return len(records)


def _salmon_version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "--version"], check=True, capture_output=True, text=True
    )
    match = re.search(r"(?<![0-9])([0-9]+\.[0-9]+\.[0-9]+)(?![0-9])", completed.stdout)
    if match is None:
        raise RuntimeError(f"Could not parse Salmon version from: {completed.stdout.strip()}.")
    return match.group(1)


def _index_checksums(index: Path) -> dict[str, str]:
    return {
        item.relative_to(index).as_posix(): _digest(item, "sha256")
        for item in sorted(index.rglob("*"))
        if item.is_file()
    }


def _validate_cached_bytes(cache: Path, manifest: dict[str, Any]) -> None:
    fixed_files = {
        "gentrome.fa": manifest["gentrome_sha256"],
        "decoys.txt": manifest["decoys_sha256"],
        "tx2gene.tsv": manifest["tx2gene_sha256"],
    }
    for relative, expected in fixed_files.items():
        path = cache / relative
        if not path.is_file() or _digest(path, "sha256") != expected:
            raise RuntimeError(f"Cached reference file drifted: {relative}.")
    for asset in manifest["assets"]:
        path = cache / "assets" / str(asset["filename"])
        if not path.is_file() or _digest(path, "sha256") != asset["local_sha256"]:
            raise RuntimeError(f"Cached reference asset drifted: {asset['filename']}.")
    index = cache / "salmon_index"
    current_files = {
        item.relative_to(index).as_posix() for item in index.rglob("*") if item.is_file()
    }
    if current_files != set(manifest["index_files"]):
        raise RuntimeError("Cached Salmon index file inventory drifted.")
    for relative, expected in manifest["index_files"].items():
        if _digest(index / relative, "sha256") != expected:
            raise RuntimeError(f"Cached Salmon index file drifted: {relative}.")


def _s3_cache_location(
    cache_uri: str,
    reference_id: str,
    definition_sha256: str,
) -> tuple[str, str]:
    parsed = urlparse(cache_uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise RuntimeError("Reference cache URI must use s3://bucket[/prefix].")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", reference_id):
        raise RuntimeError("Reference ID is unsafe for an object-cache key.")
    prefix = parsed.path.strip("/")
    parts = [
        part
        for part in (
            prefix,
            reference_id,
            definition_sha256,
            f"materialization-{MATERIALIZATION_SCHEMA_VERSION}",
        )
        if part
    ]
    return parsed.netloc, "/".join(parts)


def _cache_inventory(manifest: dict[str, Any]) -> list[str]:
    relative_paths = [
        "gentrome.fa",
        "decoys.txt",
        "tx2gene.tsv",
        *[f"assets/{item['filename']}" for item in manifest["assets"]],
        *[f"salmon_index/{relative}" for relative in manifest["index_files"]],
    ]
    for relative in relative_paths:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"Unsafe reference-cache inventory path: {relative}.")
    return sorted(set(relative_paths))


def _missing_s3_object(error: ClientError) -> bool:
    return str(error.response.get("Error", {}).get("Code")) in {
        "404",
        "NoSuchKey",
        "NotFound",
    }


def _restore_s3_cache(
    cache_uri: str,
    reference_id: str,
    definition_sha256: str,
    cache: Path,
    *,
    s3_client: Any,
) -> bool:
    bucket, prefix = _s3_cache_location(cache_uri, reference_id, definition_sha256)
    manifest_key = f"{prefix}/reference_materialization.json"
    temporary_manifest = cache / ".remote-reference-materialization.json"
    try:
        s3_client.download_file(bucket, manifest_key, str(temporary_manifest))
    except ClientError as error:
        temporary_manifest.unlink(missing_ok=True)
        if _missing_s3_object(error):
            return False
        raise
    try:
        manifest = dict(json.loads(temporary_manifest.read_text(encoding="utf-8")))
        if (
            manifest.get("reference_id") != reference_id
            or manifest.get("definition_sha256") != definition_sha256
            or manifest.get("schema_version") != MATERIALIZATION_SCHEMA_VERSION
        ):
            raise RuntimeError("S3 reference-cache manifest does not match its immutable key.")
        for relative in _cache_inventory(manifest):
            destination = cache / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.s3-partial")
            try:
                s3_client.download_file(bucket, f"{prefix}/{relative}", str(temporary))
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        _validate_cached_bytes(cache, manifest)
        temporary_manifest.replace(cache / "reference_materialization.json")
    finally:
        temporary_manifest.unlink(missing_ok=True)
    return True


def _publish_s3_cache(
    cache_uri: str,
    reference_id: str,
    definition_sha256: str,
    cache: Path,
    manifest: dict[str, Any],
    *,
    s3_client: Any,
) -> None:
    bucket, prefix = _s3_cache_location(cache_uri, reference_id, definition_sha256)
    manifest_key = f"{prefix}/reference_materialization.json"
    try:
        s3_client.head_object(Bucket=bucket, Key=manifest_key)
        return
    except ClientError as error:
        if not _missing_s3_object(error):
            raise
    for relative in _cache_inventory(manifest):
        s3_client.upload_file(str(cache / relative), bucket, f"{prefix}/{relative}")
    # The manifest is the completion marker and is uploaded last. Partially uploaded
    # prefixes are never treated as valid caches.
    s3_client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=(cache / "reference_materialization.json").read_bytes(),
        ContentType="application/json",
    )


def materialize_reference(
    definition_path: Path,
    cache_root: Path,
    output_dir: Path,
    *,
    asset_dir: Path | None = None,
    salmon_executable: str = "salmon",
    cache_uri: str | None = None,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    """Verify all source bytes and atomically build/reuse one exact Salmon index."""
    definition_bytes = definition_path.read_bytes()
    definition = dict(json.loads(definition_bytes))
    definition_sha256 = hashlib.sha256(definition_bytes).hexdigest()
    expected_version = str(definition["salmon"]["version"])
    actual_version = _salmon_version(salmon_executable)
    if actual_version != expected_version:
        raise RuntimeError(
            f"Salmon version drift: reference requires {expected_version}, executable is "
            f"{actual_version}."
        )
    roles = {str(item["role"]): item for item in definition["assets"]}
    if set(roles) != ASSET_ROLES:
        raise RuntimeError("Reference definition must contain exactly the three required assets.")

    cache = (
        cache_root
        / str(definition["reference_id"])
        / definition_sha256
        / f"materialization-{MATERIALIZATION_SCHEMA_VERSION}"
    )
    cache.mkdir(parents=True, exist_ok=True)
    remote_cache_hit = False
    if cache_uri is not None:
        client = s3_client or boto3.client("s3")
        remote_cache_hit = _restore_s3_cache(
            cache_uri,
            str(definition["reference_id"]),
            definition_sha256,
            cache,
            s3_client=client,
        )
    lock_path = cache / ".materialization.lock"
    manifest_path = cache / "reference_materialization.json"
    cache_hit = False
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if manifest_path.is_file() and (cache / "salmon_index/versionInfo.json").is_file():
            manifest = dict(json.loads(manifest_path.read_text(encoding="utf-8")))
            if (
                manifest.get("definition_sha256") != definition_sha256
                or manifest.get("salmon_version") != actual_version
            ):
                raise RuntimeError("Cached reference provenance does not match its cache key.")
            _validate_cached_bytes(cache, manifest)
            cache_hit = True
        else:
            build_dir = Path(tempfile.mkdtemp(prefix="build-", dir=cache))
            try:
                assets_dir = build_dir / "assets"
                assets_dir.mkdir()
                asset_records: list[dict[str, Any]] = []
                for role in sorted(roles):
                    asset = roles[role]
                    target = assets_dir / str(asset["filename"])
                    _materialize_asset(asset, asset_dir, target)
                    asset_records.append(
                        {
                            "role": role,
                            "filename": target.name,
                            "url": asset["url"],
                            "upstream_md5": _digest(target, "md5"),
                            "local_sha256": _digest(target, "sha256"),
                            "size_bytes": target.stat().st_size,
                        }
                    )
                transcriptome = assets_dir / str(roles["transcriptome_fasta"]["filename"])
                genome = assets_dir / str(roles["primary_assembly_genome"]["filename"])
                annotation = assets_dir / str(roles["annotation_gtf"]["filename"])
                gentrome = build_dir / "gentrome.fa"
                decoys = build_dir / "decoys.txt"
                tx2gene = build_dir / "tx2gene.tsv"
                _write_gentrome(transcriptome, genome, gentrome)
                decoy_names = _fasta_headers(genome)
                decoys.write_text("\n".join(decoy_names) + "\n", encoding="utf-8")
                mapping_count = _write_tx2gene(annotation, tx2gene)
                index = build_dir / "salmon_index"
                subprocess.run(
                    [
                        salmon_executable,
                        "index",
                        "--transcripts",
                        str(gentrome),
                        "--decoys",
                        str(decoys),
                        "--index",
                        str(index),
                        "--kmerLen",
                        str(definition["salmon"]["kmer_length"]),
                    ],
                    check=True,
                    env={**os.environ, "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"},
                )
                manifest = {
                    "schema_version": MATERIALIZATION_SCHEMA_VERSION,
                    "reference_id": definition["reference_id"],
                    "definition_sha256": definition_sha256,
                    "salmon_version": actual_version,
                    "kmer_length": definition["salmon"]["kmer_length"],
                    "index_strategy": definition["salmon"]["index_strategy"],
                    "decoy_count": len(decoy_names),
                    "transcript_gene_mapping_count": mapping_count,
                    "assets": asset_records,
                    "gentrome_sha256": _digest(gentrome, "sha256"),
                    "decoys_sha256": _digest(decoys, "sha256"),
                    "tx2gene_sha256": _digest(tx2gene, "sha256"),
                    "index_files": _index_checksums(index),
                }
                for name in ("assets", "gentrome.fa", "decoys.txt", "tx2gene.tsv", "salmon_index"):
                    source = build_dir / name
                    destination = cache / name
                    if destination.exists():
                        raise RuntimeError(f"Incomplete reference cache contains {name}.")
                    source.replace(destination)
                write_json_atomic(manifest_path, manifest)
            finally:
                shutil.rmtree(build_dir, ignore_errors=True)

        if cache_uri is not None and not remote_cache_hit:
            client = s3_client or boto3.client("s3")
            _publish_s3_cache(
                cache_uri,
                str(definition["reference_id"]),
                definition_sha256,
                cache,
                manifest,
                s3_client=client,
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cache / "tx2gene.tsv", output_dir / "tx2gene.tsv")
    result = {
        **manifest,
        "cache_hit": cache_hit,
        "cache_path": str(cache),
        "cache_uri": cache_uri,
        "cache_source": (
            "s3" if remote_cache_hit else "local" if cache_hit else "local_build"
        ),
    }
    write_json_atomic(output_dir / "reference_materialization.json", result)
    index_output = output_dir / "salmon_index"
    if index_output.is_symlink() or index_output.is_file():
        index_output.unlink()
    elif index_output.is_dir():
        shutil.rmtree(index_output)
    # Batch/S3 staging cannot safely consume a process-local symlink. Hard links
    # preserve local cache efficiency while exposing ordinary output files.
    shutil.copytree(cache / "salmon_index", index_output, copy_function=_link_or_copy)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--asset-dir", type=Path)
    parser.add_argument("--cache-uri")
    parser.add_argument("--salmon", default="salmon")
    args = parser.parse_args(argv)
    materialize_reference(
        args.definition,
        args.cache_root,
        args.output_dir,
        asset_dir=args.asset_dir,
        salmon_executable=args.salmon,
        cache_uri=args.cache_uri,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
