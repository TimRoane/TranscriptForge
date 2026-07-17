#!/usr/bin/env python3
"""Compare deterministic scientific outputs from local and AWS Batch runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _bytes_for(path: Path, comparison: str) -> bytes:
    if comparison == "sha256":
        return path.read_bytes()
    if comparison == "canonical_json":
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    raise ValueError(f"Unsupported comparison mode: {comparison}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("local_results", type=Path)
    parser.add_argument("batch_results", type=Path)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(__file__).with_name("scientific_artifact_contract.json"),
    )
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    matches = True
    for item in contract["artifacts"]:
        relative = Path(item["path"])
        local_path = args.local_results / relative
        batch_path = args.batch_results / relative
        if not local_path.is_file() or not batch_path.is_file():
            records.append(
                {
                    "path": relative.as_posix(),
                    "comparison": item["comparison"],
                    "status": "MISSING",
                    "local_present": local_path.is_file(),
                    "batch_present": batch_path.is_file(),
                }
            )
            matches = False
            continue
        local_digest = hashlib.sha256(_bytes_for(local_path, item["comparison"])).hexdigest()
        batch_digest = hashlib.sha256(_bytes_for(batch_path, item["comparison"])).hexdigest()
        status = "MATCH" if local_digest == batch_digest else "MISMATCH"
        matches &= status == "MATCH"
        records.append(
            {
                "path": relative.as_posix(),
                "comparison": item["comparison"],
                "status": status,
                "local_sha256": local_digest,
                "batch_sha256": batch_digest,
            }
        )

    result = {
        "schema_version": "1.0.0",
        "status": "MATCH" if matches else "MISMATCH",
        "contract": str(args.contract),
        "artifacts": records,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.manifest:
        args.manifest.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
