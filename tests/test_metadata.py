"""Validate repository metadata files."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_json_metadata_is_valid() -> None:
    paths = [
        ROOT / "hacs.json",
        ROOT / "custom_components/journey_guardian/manifest.json",
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


def test_package_and_manifest_versions_match() -> None:
    """HACS releases cannot advertise conflicting integration versions."""
    manifest = json.loads(
        (ROOT / "custom_components/journey_guardian/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    with (ROOT / "pyproject.toml").open("rb") as file_handle:
        package = tomllib.load(file_handle)

    assert manifest["version"] == package["project"]["version"]


def test_removed_budget_reset_action_does_not_reappear() -> None:
    """Protect the provider hard limit from a public reset bypass."""
    integration = ROOT / "custom_components/journey_guardian"
    paths = [
        integration / "__init__.py",
        integration / "const.py",
        integration / "services.yaml",
        integration / "translations/en.json",
    ]
    for path in paths:
        assert "reset_api_budget" not in path.read_text(encoding="utf-8")


def test_brand_icon_is_packaged() -> None:
    """The Home Assistant/HACS release retains the public brand asset."""
    icon = ROOT / "custom_components/journey_guardian/brand/icon.png"

    assert icon.stat().st_size > 1_000
    assert icon.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
