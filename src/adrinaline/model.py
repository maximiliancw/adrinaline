"""ADR domain model: statuses, relations, errors and parsing."""

import datetime as dt
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from ruamel.yaml.comments import CommentedMap

from adrinaline.frontmatter import FrontmatterError, split

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
    severity: str  # "error" or "warning"
    path: str
    message: str


class Frontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Status
    date: dt.date
    tags: list[str] = []
    scope: list[str] = []
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


_FIELD_CODES = {"status": "bad-status", "date": "bad-date", "scope": "bad-scope"}


def _error_code(error: Any) -> str:
    if error["type"] == "missing":
        return "missing-field"
    return _FIELD_CODES.get(str(error["loc"][0]), "bad-field")


@dataclass
class Adr:
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

    @property
    def id(self) -> str:
        return f"{self.number:04d}"


def parse_adr(path: Path, text: str) -> Adr:
    match = FILENAME_RE.match(path.name)
    if not match:
        raise AdrError("bad-filename", f"{path.name}: expected NNNN-slug.md", path=str(path))
    try:
        meta, body = split(text)
    except FrontmatterError as exc:
        raise AdrError("no-frontmatter", f"{path.name}: {exc}", path=str(path)) from exc
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
    )
