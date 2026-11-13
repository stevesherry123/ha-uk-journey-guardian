"""Check the public guide graph and the shared notification-script example."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def test_public_guide_links_resolve():
    """Follow the README's local Markdown graph without relying on Git metadata."""
    pending = [ROOT / "README.md"]
    visited = set()
    while pending:
        source = pending.pop()
        if source in visited:
            continue
        visited.add(source)
        for target in LINK.findall(source.read_text()):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            destination = (source.parent / unquote(parsed.path)).resolve()
            assert destination.is_relative_to(ROOT), (source, target)
            assert destination.is_file(), (source, target)
            if destination.suffix == ".md":
                pending.append(destination)
    assert ROOT / "docs/GETTING_STARTED.md" in visited
    assert ROOT / "docs/TRAVEL_DAY_REVIEW.md" in visited
    assert ROOT / "docs/TROUBLESHOOTING.md" in visited


def test_delivery_example_reads_the_helper_for_automatic_and_manual_alerts():
    """Automatic alerts do not pass the manual review's message variable."""
    guide = (ROOT / "docs/GETTING_STARTED.md").read_text()
    examples = re.findall(r"```yaml\n(.*?)\n```", guide, re.DOTALL)
    assert len(examples) == 1
    script = yaml.safe_load(examples[0])
    assert script["mode"] == "queued"
    step = script["sequence"][0]
    assert step["action"] == "notify.mobile_app_example_phone"
    assert step["data"]["message"] == (
        "{{ states('input_text.journey_guardian_message') }}"
    )


def test_installation_leads_with_catalogue_search_and_keeps_a_fallback():
    readme = (ROOT / "README.md").read_text()
    guide = (ROOT / "docs/GETTING_STARTED.md").read_text()
    for text in (readme, guide):
        install = text.index("**Settings → Marketplace**")
        legacy = text.index("**HACS**", install)
        search = text.index("Search for **UK Journey Guardian**", legacy)
        assert install < legacy < search

    assert readme.index("**Add from link**") > readme.index(
        "Search for **UK Journey Guardian**"
    )
    assert "**Custom repositories** in HACS" in readme
    assert "../README.md#installation" in guide
