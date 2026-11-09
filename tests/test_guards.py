import argparse
import json
from pathlib import Path

from adrinaline.cli import build_parser


def mutations(install_dir: Path) -> list[list[str]]:
    """Every mutating command once, in an order where each one succeeds."""
    return [
        ["new", "A", "--accepted"],  # 0002
        ["new", "B"],  # 0003
        ["accept", "3"],
        ["review", "3", "--until", "2099-01-01"],
        ["link", "3", "depends-on", "2"],
        ["new", "C", "--supersedes", "2"],  # 0004
        ["unlink", "3", "depends-on", "2"],
        ["renumber", "4", "--to", "9"],
        ["new", "D", "--accepted"],  # 0010
        ["new", "E", "--accepted"],  # 0011
        ["supersede", "10", "--by", "11"],
        ["new", "F"],  # 0012
        ["reject", "12"],
        ["new", "G", "--accepted"],  # 0013
        ["deprecate", "13"],
        ["new", "H", "--edit"],  # EDITOR=true in the test env
        ["init", "--force"],
        ["skill", "--install", str(install_dir)],
    ]


READS = [
    ["show", "2"],
    ["list"],
    ["index"],
    ["graph"],
    ["graph", "3", "--reverse"],
    ["check"],
    ["check", "--diff", "HEAD"],
    ["for", "src/x.py"],
    ["drift"],
    ["drift", "--at", "HEAD"],
    ["log", "1"],
    ["log", "1", "--at", "HEAD"],
    ["trace", "1"],
    ["list", "--at", "HEAD"],
    ["skill"],
    ["prime"],
    ["prime", "--budget", "50"],
]


def test_guards_exercise_every_command():
    sub = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    used = {args[0] for args in mutations(Path("x")) + READS}
    assert used == set(sub.choices)


def test_no_git_writes(initialized):  # AC15
    initialized.commit_all("baseline")
    head = initialized.git("rev-parse", "HEAD")
    index = initialized.git("ls-files", "-s")  # entries only; git may refresh its stat cache
    for args in mutations(initialized.root.parent / "skills") + READS:
        result = initialized.adr(*args)
        assert result.code in (0, 1), (args, result.err)
    assert initialized.git("rev-parse", "HEAD") == head
    assert initialized.git("ls-files", "-s") == index
    status = initialized.git("status", "--porcelain", "--untracked-files=all").splitlines()
    assert status and all(line[3:].startswith("docs/adr/") for line in status)


def test_every_command_emits_one_json_document(initialized):  # AC12
    initialized.commit_all("baseline")
    commands = [["init"], *mutations(initialized.root.parent / "skills"), *READS]
    for args in [*commands, ["show", "404"], ["accept", "1"]]:
        result = initialized.adr(*args, "--json")
        assert result.code in (0, 1, 3), (args, result.err)
        json.loads(result.out)
