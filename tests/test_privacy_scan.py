"""The repository and release scans cover frontend code and unknown suffixes."""

import subprocess
import sys
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile

SCANNER = Path(__file__).resolve().parents[1] / "scripts" / "privacy_scan.py"


def test_tracked_text_and_archive_members_are_checked(tmp_path):
    subprocess.run(["git", "init", "-q", tmp_path], check=True)
    scanner = tmp_path / "scripts" / SCANNER.name
    scanner.parent.mkdir()
    copyfile(SCANNER, scanner)
    marker = "ghp_" + "x" * 32
    path = tmp_path / "example.js"
    path.write_text(marker)
    subprocess.run(["git", "add", path.name], cwd=tmp_path, check=True)
    archive = tmp_path / "release.zip"
    with ZipFile(archive, "w") as out:
        out.writestr("nested/example.unknown", marker)
    for args in ([], ["--archive", str(archive)]):
        result = subprocess.run(
            [sys.executable, scanner, *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "classic GitHub token" in result.stdout
        assert marker not in result.stdout
