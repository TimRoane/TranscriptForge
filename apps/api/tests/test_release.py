"""Release identity validation coverage."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[3]
VALIDATOR = ROOT / "scripts/validate_release.py"


def test_release_versions_and_tag_are_consistent() -> None:
    valid = subprocess.run(
        [sys.executable, str(VALIDATOR), "--tag", "v0.1.0"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert valid.returncode == 0
    assert "version 0.1.0 is consistent" in valid.stdout

    mismatch = subprocess.run(
        [sys.executable, str(VALIDATOR), "--tag", "v1.0.0"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert mismatch.returncode != 0
    assert "does not match application version" in mismatch.stderr
