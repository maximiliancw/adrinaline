"""Human and JSON output, the error envelope and exit codes."""

import json
import sys
from pathlib import Path
from typing import Any

from adrinaline.model import STORED_RELATIONS, Adr, AdrError, Status

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_DOMAIN = 3

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


class Out:
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
    if json_mode:
        envelope = {"error": {"code": err.code, "message": err.message, "details": err.details}}
        sys.stdout.write(dumps(envelope) + "\n")
    else:
        print(f"adr: {err.code}: {err.message}", file=sys.stderr)
    return EXIT_DOMAIN
