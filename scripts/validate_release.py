#!/usr/bin/env python3
"""Validate synchronized application versions and an optional release tag."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Expected release tag, for example v0.1.0")
    return parser.parse_args()


def load_versions() -> dict[str, str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    root_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    web_package = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
    api_source = (ROOT / "apps/api/transcriptforge_api/__init__.py").read_text(
        encoding="utf-8"
    )
    api_match = re.search(r'^__version__ = "([^"]+)"$', api_source, flags=re.MULTILINE)
    if api_match is None:
        raise SystemExit("Could not read the API __version__ value.")
    return {
        "pyproject": str(pyproject["project"]["version"]),
        "root package": str(root_package["version"]),
        "web package": str(web_package["version"]),
        "API package": api_match.group(1),
    }


def main() -> None:
    options = arguments()
    versions = load_versions()
    unique_versions = set(versions.values())
    if len(unique_versions) != 1:
        detail = ", ".join(f"{name}={version}" for name, version in versions.items())
        raise SystemExit(f"Application versions disagree: {detail}")
    version = unique_versions.pop()
    if options.tag is not None:
        match = SEMVER_TAG.fullmatch(options.tag)
        if match is None:
            raise SystemExit(
                "Release tags must use stable semantic version form vMAJOR.MINOR.PATCH."
            )
        if options.tag != f"v{version}":
            raise SystemExit(
                f"Release tag {options.tag} does not match application version {version}."
            )
    print(f"TranscriptForge release version {version} is consistent.")


if __name__ == "__main__":
    main()
