"""Fail when repository text resembles secrets or installation-specific IDs."""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).parents[1]
PATTERNS = {
    "GitHub personal access token": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "classic GitHub token": re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    "JSON web token": re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
    "concrete person entity": re.compile(r"\bperson\.[a-z0-9_]+\b"),
    "concrete calendar entity": re.compile(r"\bcalendar\.[a-z0-9_]+\b"),
    "configuration entry identifier": re.compile(
        r"\b[0-9A-HJKMNP-TV-Z]{26}\b"
    ),
    "private key material": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
}


def main() -> int:
    """Check tracked files or a built archive without printing matched values."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    rules = dict(PATTERNS)
    private = subprocess.check_output(
        ["git", "rev-parse", "--git-path", "info/jg-private-patterns"],
        cwd=ROOT, text=True,
    ).strip()
    private_file = ROOT / private
    if private_file.is_file():
        for index, pattern in enumerate(private_file.read_text().splitlines()):
            if pattern:
                rules[f"local rule {index + 1}"] = re.compile(pattern)

    def check(name: str, data: bytes) -> bool:
        # Latin-1 preserves every byte, including ASCII identifiers in binary files.
        content = data.decode("latin-1")
        clean = True
        for label, pattern in rules.items():
            if pattern.search(content):
                print(f"privacy scan: {name!r}: {label}")
                clean = False
        return clean

    clean = True
    if args.archive:
        with ZipFile(args.archive) as archive:
            for member in archive.infolist():
                clean = check(member.filename, archive.read(member)) and clean
    else:
        paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
        for raw in paths.split(b"\0"):
            if raw:
                name = os.fsdecode(raw)
                path = ROOT / name
                data = (
                    os.fsencode(os.readlink(path)) if path.is_symlink()
                    else path.read_bytes()
                )
                clean = check(name, data) and clean
    if clean:
        print("privacy scan: clean")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
