import datetime as dt
from pathlib import Path

from adrinaline import drift, git
from adrinaline.git import Commit
from adrinaline.repo import parse_all


def adrs_of(*specs: tuple[int, str, str, str]):
    """(number, status, date, extra frontmatter lines)."""
    items = []
    for n, status, date, extra in specs:
        front = f"status: {status}\ndate: {date}\n{extra}"
        items.append((Path(f"d/{n:04d}-a{n}.md"), f"---\n{front}---\n# Decision {n}\n"))
    return parse_all(items).adrs


D = dt.date


def test_compute_counts_scoped_commits_after_the_baseline():
    adrs = adrs_of(
        (1, "accepted", "2026-01-15", 'scope: ["src/db/**"]\n'),
        (2, "accepted", "2026-01-15", ""),
        (3, "accepted", "2026-01-15", 'scope: ["src/**"]\nreviewed: 2026-03-01\n'),
    )
    commits = [
        Commit("c3", D(2026, 3, 2), "pool", ("src/db/pool.py",)),
        Commit("c2", D(2026, 2, 1), "conn", ("src/db/conn.py", "README.md")),
        Commit("c1", D(2026, 1, 15), "same day as baseline", ("src/db/conn.py",)),
        Commit("c0", D(2026, 1, 1), "before", ("src/db/conn.py",)),
    ]
    result = drift.compute(adrs, commits)
    assert [(d.adr.number, len(d.commits)) for d in result] == [(1, 2), (3, 1)]
    assert result[0].files == ["src/db/conn.py", "src/db/pool.py"]
    assert result[0].last is not None and result[0].last.sha == "c3"
    assert result[1].last is not None and result[1].last.sha == "c3"  # reviewed 03-01 excludes c2


def test_earliest_baseline_ignores_unscoped_adrs():
    adrs = adrs_of(
        (1, "accepted", "2026-01-01", ""),
        (2, "accepted", "2026-02-01", 'scope: ["src/**"]\nreviewed: 2026-05-01\n'),
        (3, "accepted", "2026-03-01", 'scope: ["docs/**"]\n'),
    )
    assert drift.earliest_baseline(adrs) == D(2026, 3, 1)
    assert drift.earliest_baseline(adrs_of((1, "accepted", "2026-01-01", ""))) is None


def test_review_findings():
    adrs = adrs_of(
        (1, "accepted", "2026-01-15", "review-by: 2026-06-01\n"),
        (2, "accepted", "2026-01-15", 'scope: ["src/**"]\n'),
        (3, "accepted", "2026-01-15", "review-by: 2099-01-01\n"),
    )
    commits = [
        Commit("c", D(2026, 2, 1), "s", ("src/a.py",)),
        Commit("d", D(2026, 2, 2), "t", ("src/b.py",)),
    ]
    drifts = drift.compute(adrs, commits)
    today = D(2026, 11, 8)
    codes = [(f.code, f.path) for f in drift.review_findings(adrs, drifts, today, threshold=2)]
    assert codes == [("review-overdue", "d/0001-a1.md"), ("stale-decision", "d/0002-a2.md")]
    assert [f.code for f in drift.review_findings(adrs, drifts, today, threshold=3)] == [
        "review-overdue"
    ]
    assert [f.code for f in drift.review_findings(adrs, drifts, today, threshold=0)] == [
        "review-overdue"
    ]
    overdue = drift.review_findings(adrs, drifts, today, threshold=0)[0]
    assert "2026-06-01" in overdue.message and "adr review 1" in overdue.message
    stale = drift.review_findings(adrs, drifts, today, threshold=2)[1]
    assert (
        "2 commits" in stale.message
        and "2026-01-15" in stale.message
        and "adr review 2" in stale.message
    )


def test_commits_since_reads_files_dates_and_subjects(ws):
    ws.write("src/a.py", "1\n")
    ws.commit_all("first")
    ws.write("src/b.py", "1\n")
    ws.write("docs/x.md", "1\n")
    ws.commit_all("second line")  # contains U+2028: str.splitlines() would split it, "\n" must not
    commits = git.commits_since(ws.root, D(2000, 1, 1))
    assert [c.subject for c in commits] == ["second line", "first"]
    assert commits[0].files == ("docs/x.md", "src/b.py")
    assert commits[0].date == dt.date.today()
    assert all(len(c.sha) == 40 for c in commits)


def test_commits_since_at_revision(ws):
    ws.write("src/a.py", "1\n")
    ws.commit_all("first")
    ws.write("src/b.py", "1\n")
    ws.commit_all("second")
    assert [c.subject for c in git.commits_since(ws.root, D(2000, 1, 1), "HEAD~1")] == ["first"]


def test_commits_since_without_commits(ws):
    assert git.commits_since(ws.root, D(2000, 1, 1)) == []


def test_drift_cli(initialized):  # AC26
    w = initialized
    w.write_adr(2, "db", scope=["src/db/**"])
    w.write_adr(3, "unscoped")
    w.commit_all("adrs")
    w.write("src/db/conn.py", "1\n")
    w.commit_all("db one")
    w.write("src/db/pool.py", "1\n")
    w.commit_all("db two")
    w.write("src/other/x.py", "1\n")
    w.commit_all("other")
    data = w.adr("drift", "--json").json()
    assert [(d["number"], d["commits"]) for d in data] == [(2, 2)]
    assert data[0]["files"] == ["src/db/conn.py", "src/db/pool.py"]
    assert data[0]["last"]["subject"] == "db two" and data[0]["baseline"] == "2026-01-15"
    assert set(data[0]) == {
        "number",
        "id",
        "title",
        "baseline",
        "review-by",
        "revisit-if",
        "commits",
        "files",
        "last",
    }
    text = w.adr("drift").out
    assert text.startswith("0002  Db  2 commits / 2 files since 2026-01-15  last: ")
    assert "db two" in text and "2 in force without scope" in text
    assert w.adr("review", "2").code == 0
    w.commit_all("reviewed")
    assert w.adr("drift", "--json").json()[0]["commits"] == 0
    assert w.adr("drift", "--at", "HEAD~1", "--json").json()[0]["commits"] == 2
    assert w.adr("drift", "2", "--json").json()[0]["number"] == 2
    assert w.adr("drift", "3", "--json").json() == []


def test_drift_needs_git(tmp_path):
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    from adrinaline.cli import main

    assert main(["drift", "--json"], cwd=tmp_path, env={}) == 3


def test_drift_bad_revision(initialized):
    result = initialized.adr("drift", "--at", "nope", "--json")
    assert result.code != 0 and "bad-revision" in result.out
