from __future__ import annotations

import sys
from pathlib import Path

import pytest

from buildkit.verify_portable_exit import verify_exit


@pytest.mark.parametrize(
    "scenario", ["plain", "floating", "dialogs", "auxiliary", "save", "cancel"]
)
def test_real_entrypoint_releases_process_after_close(
    *, scenario: str, tmp_path: Path
) -> None:
    root = Path(__file__).resolve().parents[2]
    result = verify_exit(
        command=[sys.executable, str(root / "buildkit/portable_entry.py")],
        scenario=scenario,
        directory=tmp_path / scenario,
        image=root / "tests/data/raw/2011_000003.jpg",
    )
    assert result["ok"], result
