"""Verify the archive layout HACS extracts directly into the integration folder."""

import json
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile

ROOT = Path(__file__).parents[1]
build_release = run_path(str(ROOT / "scripts/build_release.py"))["build_release"]


def test_release_is_deterministic_flat_runtime_only_and_version_aligned(tmp_path):
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    build_release(first)
    build_release(second)
    assert first.read_bytes() == second.read_bytes()
    with ZipFile(first) as archive:
        names = archive.namelist()
        assert archive.testzip() is None
        assert "__init__.py" in names
        assert "brand/icon.png" in names
        assert "translations/en.json" in names
        assert "health_issues.py" in names
        assert not any(
            part in {"tests", "docs", "__pycache__", "custom_components"}
            or part.startswith(".")
            for name in names
            for part in Path(name).parts
        )
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest == json.loads(
            (ROOT / "custom_components/journey_guardian/manifest.json").read_text()
        )
        assert manifest["domain"] == "journey_guardian"
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["zip_release"] is True
    assert hacs["filename"] == "journey_guardian.zip"
