"""The init and new wizards, run in-process with a fake terminal."""

import builtins

import pytest
from conftest import ENV

from adrinaline import cli


@pytest.fixture
def terminal(monkeypatch):
    def answer(*answers: str) -> None:
        feed = iter(answers)
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr(builtins, "input", lambda prompt: next(feed))

    return answer


def test_init_asks_before_each_wiring_step(tmp_path, terminal, capsys):
    terminal("n", "y")
    assert cli.main(["init"], cwd=tmp_path, env=ENV) == 0
    assert not (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".agents/skills/adr/SKILL.md").exists()
    out = capsys.readouterr().out
    assert "wrote .agents/skills/adr/SKILL.md" in out and "adr skill --install" not in out


def test_new_prompts_for_title_supersedes_and_scope(tmp_path, terminal):
    assert cli.main(["init", "--json"], cwd=tmp_path, env=ENV) == 0
    terminal("", "Use PostgreSQL", "1", "src/db/** src/models/**")
    assert cli.main(["new", "--force"], cwd=tmp_path, env=ENV) == 0
    text = (tmp_path / "docs/adr/0002-use-postgresql.md").read_text()
    assert "supersedes: [1]" in text and "scope: [src/db/**, src/models/**]" in text
    assert "superseded" in (tmp_path / "docs/adr/0001-record-architecture-decisions.md").read_text()


def test_new_does_not_reprompt_given_flags(tmp_path, terminal):
    assert cli.main(["init", "--json"], cwd=tmp_path, env=ENV) == 0
    terminal("Only the title", "")  # scope is not asked again
    assert cli.main(["new", "--scope", "src/**"], cwd=tmp_path, env=ENV) == 0
    assert "scope: [src/**]" in (tmp_path / "docs/adr/0002-only-the-title.md").read_text()


def test_closed_input_aborts_instead_of_looping(tmp_path, monkeypatch, capsys):
    assert cli.main(["init", "--json"], cwd=tmp_path, env=ENV) == 0
    monkeypatch.setattr(cli, "_interactive", lambda: True)

    def closed(prompt):
        raise EOFError

    monkeypatch.setattr(builtins, "input", closed)
    assert cli.main(["new"], cwd=tmp_path, env=ENV) == 3
    assert "input closed" in capsys.readouterr().err
    assert not list((tmp_path / "docs/adr").glob("0002-*"))


def test_new_json_on_a_terminal_does_not_prompt(tmp_path, terminal, capsys):
    assert cli.main(["init", "--json"], cwd=tmp_path, env=ENV) == 0
    terminal("never asked")
    with pytest.raises(SystemExit) as exc:
        cli.main(["new", "--json"], cwd=tmp_path, env=ENV)
    assert exc.value.code == 2 and "title" in capsys.readouterr().err


def test_init_skill_hint_is_relative_to_cwd(tmp_path):
    sub = tmp_path / "pkg"
    sub.mkdir()
    (tmp_path / ".git").mkdir()  # not a real repo: locate() falls back to cwd as base
    assert cli.main(["init", "--json"], cwd=sub, env=ENV) == 0
