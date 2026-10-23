"""Build a deterministic, runtime-only HACS installation asset."""

import argparse
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = Path("custom_components/journey_guardian")
SUFFIXES = {".py", ".json", ".yaml", ".png", ".js"}


def build_release(output: Path, *, root: Path = ROOT) -> None:
    """Use tracked files only; never package caches or private local extras."""
    tracked = (
        subprocess.run(
            ["git", "ls-files", "-z", "--", str(INTEGRATION)],
            cwd=root,
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .split("\0")
    )
    files = []
    for value in sorted(filter(None, tracked)):
        path = Path(value)
        relative = path.relative_to(INTEGRATION)
        if (
            (root / path).is_symlink()
            or any(
                part.startswith(".") or part == "__pycache__" for part in relative.parts
            )
            or path.suffix not in SUFFIXES
        ):
            raise ValueError("unsupported_release_file")
        files.append((root / path, relative.as_posix()))
    if not {"manifest.json", "__init__.py", "services.yaml"}.issubset(
        name for _path, name in files
    ):
        raise ValueError("missing_runtime_files")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path, name in files:
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist/journey_guardian.zip"
    )
    build_release(parser.parse_args().output)
