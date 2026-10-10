"""Fail when repository text resembles secrets or installation-specific IDs."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "venv",
}
TEXT_SUFFIXES = {
    "",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

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
    "private route place": re.compile(
        "|".join(
            (
                "ches" + "ter",
                "cre" + "we",
                "liverpool lime " + "street",
                "london " + "eus" + "ton",
                "man" + "ches" + "ter",
                "holy" + "head",
                "wrex" + "ham",
            )
        ),
        re.IGNORECASE,
    ),
    "private coordinates": re.compile(
        r"\b(?:53\.2|-2\.9|51\.5|-0\.1)\b"
    ),
    "private route station code": re.compile(
        rf"\b(?:{'|'.join(('E' + 'US', 'C' + 'TR', 'C' + 'RE', 'L' + 'IV'))})\b"
    ),
}


def main() -> int:
    """Scan repository text and print only file and rule names."""
    findings: list[tuple[Path, str]] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(
            part in EXCLUDED_PARTS or part.endswith(".egg-info")
            for part in path.parts
        ):
            continue
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append((path.relative_to(ROOT), name))

    if findings:
        for path, name in findings:
            print(f"privacy scan: {path}: {name}")
        return 1
    print("privacy scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
