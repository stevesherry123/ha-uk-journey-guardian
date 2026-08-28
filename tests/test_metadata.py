"""Validate repository metadata files."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_json_metadata_is_valid() -> None:
    paths = [
        ROOT / "hacs.json",
        ROOT / "custom_components/journey_guardian/manifest.json",
        ROOT / "custom_components/journey_guardian/strings.json",
        ROOT / "custom_components/journey_guardian/translations/en.json",
    ]
    for path in paths:
        with path.open(encoding="utf-8") as file_handle:
            assert isinstance(json.load(file_handle), dict)


def test_manifest_contains_no_embedded_credentials() -> None:
    manifest = (
        ROOT / "custom_components/journey_guardian/manifest.json"
    ).read_text(encoding="utf-8")
    assert "app_key" not in manifest.casefold()
    assert "github_pat_" not in manifest.casefold()
