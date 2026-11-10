"""ADR domain model: statuses, relations, errors and parsing."""

import datetime as dt
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from ruamel.yaml.comments import CommentedMap

from adrinaline.frontmatter import (
    FrontmatterDateError,
    FrontmatterError,
    FrontmatterMissing,
    split,
)

FILENAME_RE = re.compile(r"^(\d{4,})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")


class Status(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


TRANSITIONS = frozenset(
    {
        (Status.PROPOSED, Status.ACCEPTED),
        (Status.PROPOSED, Status.REJECTED),
        (Status.ACCEPTED, Status.DEPRECATED),
        (Status.ACCEPTED, Status.SUPERSEDED),
    }
)
"""Status changes allowed without `--force`, as `(from, to)` pairs."""

STORED_RELATIONS = ("supersedes", "superseded-by", "amends", "depends-on", "relates-to")
LINKABLE = ("amends", "depends-on", "relates-to")
INVERSE = {
    "supersedes": "superseded-by",
    "amends": "amended-by",
    "depends-on": "dependency-of",
    "relates-to": "relates-to",
}


class AdrError(Exception):
    """A domain error with a stable machine-readable code (exit code 3)."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "error", "warning" or "note"
    path: str
    message: str


class Frontmatter(BaseModel):
    """Validated frontmatter. Hyphenated YAML keys fill the snake_case fields; the snake_case
    spellings are not read and fall into the extra keys. Other unknown keys are kept as well."""

    model_config = ConfigDict(extra="allow")

    status: Status
    date: dt.date
    tags: list[str] = []
    scope: list[str] = []
    review_by: dt.date | None = Field(default=None, alias="review-by")
    reviewed: dt.date | None = None
    revisit_if: str | None = Field(default=None, alias="revisit-if")
    supersedes: list[int] = []
    superseded_by: list[int] = Field(default=[], alias="superseded-by")
    amends: list[int] = []
    depends_on: list[int] = Field(default=[], alias="depends-on")
    relates_to: list[int] = Field(default=[], alias="relates-to")

    @field_validator("scope")
    @classmethod
    def _relative_globs(cls, globs: list[str]) -> list[str]:
        for glob in globs:
            if glob.startswith("/") or ".." in PurePosixPath(glob).parts:
                raise ValueError(f"scope glob must be repository-relative: {glob}")
        return globs


_FIELD_CODES = {
    "status": "bad-status",
    "date": "bad-date",
    "review-by": "bad-date",
    "reviewed": "bad-date",
    "scope": "bad-scope",
}


def _error_code(error: Any) -> str:
    if error["type"] == "missing":
        return "missing-field"
    return _FIELD_CODES.get(str(error["loc"][0]), "bad-field")


@dataclass
class Adr:
    """One parsed ADR file.

    `meta` is the round-trip frontmatter that gets written back; `relations` always has the five
    `STORED_RELATIONS` keys. `text` is the whole file as read and `body` what follows the
    frontmatter; `number` and `slug` come from the filename, `title` from the first `# ` heading.
    """

    number: int
    slug: str
    path: Path
    title: str
    status: Status
    date: dt.date
    tags: list[str]
    scope: list[str]
    relations: dict[str, list[int]]
    meta: CommentedMap
    body: str
    text: str
    review_by: dt.date | None = None
    reviewed: dt.date | None = None
    revisit_if: str | None = None

    @property
    def id(self) -> str:
        return f"{self.number:04d}"

    @property
    def baseline(self) -> dt.date:
        """Start of the drift window: the later of date and reviewed (SPEC §8)."""
        return max(self.date, self.reviewed) if self.reviewed else self.date


_NYGARD_STATUS = re.compile(
    r"^#{1,6}[ \t]*Status[ \t]*\r?\n(?:[ \t]*\r?\n)*[ \t]*(\w+)", re.M | re.I
)
_ADR_TOOLS_DATE = re.compile(r"^Date:[ \t]*(\d{4}-\d{2}-\d{2})[ \t]*\r?$", re.M)
# superseded is left out: `adr check` needs a `superseded-by` relation with it (status-mismatch)
_HINTABLE_STATUSES = {s.value for s in Status} - {Status.SUPERSEDED}


def _import_hint(text: str) -> str:
    """What an adr-tools or Nygard file needs to become an ADR, read from its own header."""
    status = _NYGARD_STATUS.search(text)
    word = status[1].lower() if status else ""
    date = _ADR_TOOLS_DATE.search(text)
    try:
        day = dt.date.fromisoformat(date[1]).isoformat() if date else "<YYYY-MM-DD>"
    except ValueError:
        day = "<YYYY-MM-DD>"
    return (
        f"add frontmatter with status: {word if word in _HINTABLE_STATUSES else '<status>'}"
        f" and date: {day}"
    )


def parse_adr(path: Path, text: str) -> Adr:
    """Parse one ADR; `path` supplies the number and slug. Raises `AdrError` with code:

    `bad-filename`; `no-frontmatter` (missing, unterminated, invalid YAML or not a mapping);
    `bad-date` (unparseable date, or a bad `date`, `review-by` or `reviewed` value);
    `missing-field`; `bad-status`; `bad-scope`; `bad-field` (any other invalid field); `no-title`.
    Only the first validation error is reported.
    """
    match = FILENAME_RE.match(path.name)
    if not match:
        raise AdrError("bad-filename", f"{path.name}: expected NNNN-slug.md", path=str(path))
    try:
        meta, body = split(text)
    except FrontmatterDateError as exc:
        raise AdrError("bad-date", f"{path.name}: {exc}", path=str(path)) from exc
    except FrontmatterError as exc:
        # a BOM or blank line before a real `---` block is not an import: no hint
        has_block = text.lstrip("\ufeff \t\r\n").startswith("---")
        hint = (
            f"; {_import_hint(text)}"
            if isinstance(exc, FrontmatterMissing) and not has_block
            else ""
        )
        raise AdrError("no-frontmatter", f"{path.name}: {exc}{hint}", path=str(path)) from exc
    try:
        front = Frontmatter.model_validate(dict(meta))
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise AdrError(
            _error_code(first), f"{path.name}: {where}: {first['msg']}", path=str(path)
        ) from exc
    title = next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), "")
    if not title:
        raise AdrError("no-title", f"{path.name}: no '# ' title heading", path=str(path))
    relations = {name: list(getattr(front, name.replace("-", "_"))) for name in STORED_RELATIONS}
    return Adr(
        number=int(match[1]),
        slug=match[2],
        path=path,
        title=title,
        status=front.status,
        date=front.date,
        tags=front.tags,
        scope=front.scope,
        relations=relations,
        meta=meta,
        body=body,
        text=text,
        review_by=front.review_by,
        reviewed=front.reviewed,
        revisit_if=front.revisit_if,
    )
