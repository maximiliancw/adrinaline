import adrinaline


def test_version_is_set():
    assert adrinaline.__version__


def test_skill_install(tmp_path):
    from adrinaline import __version__
    from adrinaline.cli import main
    from adrinaline.repo import data_text

    dest = tmp_path / ".claude" / "skills" / "adr"
    assert main(["skill", "--install", ".claude/skills/adr", "--json"], cwd=tmp_path) == 0
    for name in ("SKILL.md", "references/frontmatter.md"):
        assert (dest / name).read_text(encoding="utf-8") == data_text(name).replace(
            "{version}", __version__
        )
    assert f'version: "{__version__}"' in (dest / "SKILL.md").read_text(encoding="utf-8")
