import argparse
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from adrinaline.cli import build_parser

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)], cwd=ROOT, check=True, capture_output=True
    )
    return out


def test_wheel_contains_data_files(dist):
    wheel = next(dist.glob("adrinaline-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    for data in (
        "template.md",
        "0001.md",
        "skills/adr/SKILL.md",
        "skills/adr/references/frontmatter.md",
    ):
        assert f"adrinaline/data/{data}" in names


def test_pre_commit_hook_definition():
    (hook,) = YAML(typ="safe").load((ROOT / ".pre-commit-hooks.yaml").read_text())
    assert hook["id"] == "adr-check"
    assert hook["entry"] == "adr check --strict"
    assert hook["pass_filenames"] is False
    assert hook["files"] == "^docs/adr/"


def test_cli_reference_lists_every_command():
    page = (ROOT / "docs/cli.md").read_text()
    sub = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    for name, parser in sub.choices.items():
        assert f"`{name}" in page, name
        for action in parser._actions:
            for flag in action.option_strings:
                if flag.startswith("--") and flag != "--help":
                    assert flag in page, f"{name} {flag}"


def test_plugin_manifests_point_at_the_packaged_skill():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert (ROOT / plugin["skills"] / "adr/SKILL.md").is_file()
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert [p["name"] for p in market["plugins"]] == [plugin["name"]]
    hooks = json.loads((ROOT / "hooks/hooks.json").read_text())
    [entry] = hooks["hooks"]["SessionStart"]
    assert "adr prime" in entry["hooks"][0]["command"]
