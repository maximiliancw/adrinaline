"""Human and JSON output, the error envelope and exit codes."""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from adrinaline.model import STORED_RELATIONS, Adr, AdrError, Status

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_DOMAIN = 3

# Keep in sync with model.Frontmatter: the keys adr_dict renders as fields, so not under `meta`.
_KNOWN_KEYS = {
    "status",
    "date",
    "tags",
    "scope",
    "review-by",
    "reviewed",
    "revisit-if",
    *STORED_RELATIONS,
}
_STYLES = {"red": "31", "green": "32", "yellow": "33", "bold": "1", "dim": "2"}
STATUS_STYLE = {Status.ACCEPTED: "green", Status.PROPOSED: "yellow"}  # the rest are dim


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


_GITHUB_LEVEL = {"error": "error", "warning": "warning", "note": "notice"}
_GITLAB_SEVERITY = {"error": "major", "warning": "minor", "note": "info"}


def _gh_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _gh_prop(text: str) -> str:
    return _gh_data(text).replace(":", "%3A").replace(",", "%2C")


def github_annotation(row: dict[str, str]) -> str:
    """One GitHub Actions workflow command for a `check` finding."""
    props = [f"file={_gh_prop(row['path'])}", "line=1"] if row["path"] else []
    props.append(f"title={_gh_prop(row['code'])}")
    return f"::{_GITHUB_LEVEL[row['severity']]} {','.join(props)}::{_gh_data(row['message'])}"


def gitlab_report(rows: list[dict[str, str]], fallback: str) -> str:
    """A GitLab Code Quality report for `check` findings; set-wide ones point at `fallback`.

    Fingerprints hash code, path and occurrence index, not the message, which carries
    volatile text such as commit hashes and churn counts.
    """
    seen: dict[tuple[str, str], int] = {}
    issues = []
    for r in rows:
        key = (r["code"], r["path"])
        seen[key] = n = seen.get(key, -1) + 1
        issues.append(
            {
                "description": r["message"],
                "check_name": r["code"],
                "fingerprint": hashlib.sha256(f"{key[0]}\0{key[1]}\0{n}".encode()).hexdigest(),
                "severity": _GITLAB_SEVERITY[r["severity"]],
                "location": {"path": r["path"] or fallback, "lines": {"begin": 1}},
            }
        )
    return dumps(issues)


class Out:
    """Output channel. `result` prints JSON in `json_mode`, else the text unless `quiet`; `note`
    writes a hint to stderr unless `quiet`; `rel` shortens a path relative to `base`; `paint` adds
    ANSI colour only when `color` is set."""

    def __init__(self, *, json_mode: bool, quiet: bool, base: Path, color: bool = False) -> None:
        self.json_mode = json_mode
        self.quiet = quiet
        self.base = base.resolve()
        self.color = color

    def paint(self, text: str, style: str) -> str:
        return f"\x1b[{_STYLES[style]}m{text}\x1b[0m" if self.color else text

    def status(self, status: Status, width: int = 0) -> str:
        return self.paint(f"{status:<{width}}", STATUS_STYLE.get(status, "dim"))

    def rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.base).as_posix()
        except ValueError:
            return str(path)

    def result(self, data: Any, text: str) -> None:
        if self.json_mode:
            sys.stdout.write(dumps(data) + "\n")
        elif not self.quiet and text:
            sys.stdout.write(text if text.endswith("\n") else text + "\n")

    def note(self, text: str) -> None:
        if not self.quiet:
            print(text, file=sys.stderr)


def adr_dict(
    adr: Adr,
    out: Out,
    *,
    relations: dict[str, list[int]] | None = None,
    body: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """The JSON object for one ADR.

    `relations` defaults to the stored relations that are not empty; pass one to show others, such
    as derived inverses. `meta` holds the frontmatter keys that have no field of their own. `body`
    adds the Markdown body; `extra` is merged last and wins on a clash.
    """
    data: dict[str, Any] = {
        "number": adr.number,
        "id": adr.id,
        "slug": adr.slug,
        "title": adr.title,
        "status": adr.status.value,
        "date": adr.date.isoformat(),
        "path": out.rel(adr.path),
        "tags": list(adr.tags),
        "scope": list(adr.scope),
        "review-by": adr.review_by.isoformat() if adr.review_by else None,
        "reviewed": adr.reviewed.isoformat() if adr.reviewed else None,
        "revisit-if": adr.revisit_if,
        "relations": relations
        if relations is not None
        else {name: nums for name, nums in adr.relations.items() if nums},
        "meta": {k: v for k, v in adr.meta.items() if k not in _KNOWN_KEYS},
    }
    if body:
        data["body"] = adr.body
    return data | extra


def error(err: AdrError, json_mode: bool) -> int:
    """Report `err`: a JSON envelope on stdout, or `adr: code: message` on stderr. Returns the
    domain exit code (3)."""
    if json_mode:
        envelope = {"error": {"code": err.code, "message": err.message, "details": err.details}}
        sys.stdout.write(dumps(envelope) + "\n")
    else:
        print(f"adr: {err.code}: {err.message}", file=sys.stderr)
    return EXIT_DOMAIN
