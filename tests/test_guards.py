import json

MUTATIONS = [
    ["new", "A", "--accepted"],
    ["new", "B"],
    ["accept", "3"],
    ["link", "3", "depends-on", "2"],
    ["new", "C", "--supersedes", "2"],
    ["unlink", "3", "depends-on", "2"],
    ["renumber", "4", "--to", "9"],
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
    ["log", "1"],
    ["list", "--at", "HEAD"],
    ["skill"],
    ["prime"],
    ["prime", "--budget", "50"],
]


def test_no_git_writes(initialized):  # AC15
    initialized.commit_all("baseline")
    head = initialized.git("rev-parse", "HEAD")
    index = (initialized.root / ".git" / "index").read_bytes()
    for args in MUTATIONS + READS:
        result = initialized.adr(*args)
        assert result.code in (0, 1), (args, result.err)
    assert initialized.git("rev-parse", "HEAD") == head
    assert (initialized.root / ".git" / "index").read_bytes() == index
    status = initialized.git("status", "--porcelain", "--untracked-files=all").splitlines()
    assert status and all(line[3:].startswith("docs/adr/") for line in status)


def test_every_command_emits_one_json_document(initialized):  # AC12
    initialized.commit_all("baseline")
    for args in [["init"], *MUTATIONS, *READS, ["show", "404"], ["accept", "1"]]:
        result = initialized.adr(*args, "--json")
        assert result.code in (0, 1, 3), (args, result.err)
        json.loads(result.out)
