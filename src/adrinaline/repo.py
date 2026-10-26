"""Locate the ADR directory, load ADRs, resolve references and write files."""

import datetime as dt
import os
import re
import shutil
import tempfile
import tomllib
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from adrinaline import git
from adrinaline.frontmatter import FrontmatterError, flow, render, split
from adrinaline.graph import ACYCLIC, AdrGraph, Edge
from adrinaline.model import (
    FILENAME_RE,
    LINKABLE,
    TRANSITIONS,
    Adr,
    AdrError,
    Finding,
    Status,
    parse_adr,
)

__all__ = ["flow"]


@dataclass(frozen=True)
class Location:
    dir: Path
    root: Path | None
    template: Path


@dataclass
class AdrSet:
    adrs: list[Adr]
    problems: list[Finding]
    numbers: set[int]


def _ancestors(start: Path, top: Path | None) -> Iterator[Path]:
    for directory in (start, *start.parents):
        yield directory
        if directory == top:
            return


def _toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as exc:
        raise AdrError("bad-config", f"{path}: {exc}", path=str(path)) from exc


def _config_table(directory: Path) -> dict | None:
    dedicated = directory / ".adrinaline.toml"
    if dedicated.is_file():
        return _toml(dedicated)
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        return _toml(pyproject).get("tool", {}).get("adrinaline")
    return None


def locate(cwd: Path, env: Mapping[str, str], explicit: Path | None = None) -> Location:
    root = git.toplevel(cwd)
    table: dict = {}
    base = cwd
    for directory in _ancestors(cwd, root):
        found = _config_table(directory)
        if found:
            table, base = found, directory
            break
    adr_dir_file = next(
        (d / ".adr-dir" for d in _ancestors(cwd, root) if (d / ".adr-dir").is_file()), None
    )
    for key in ("dir", "template"):
        if key in table and not isinstance(table[key], str):
            raise AdrError("bad-config", f"config key {key!r} must be a string")
    if explicit is not None:
        directory = cwd / explicit
    elif env.get("ADR_DIR"):
        directory = cwd / env["ADR_DIR"]
    elif "dir" in table:
        directory = base / table["dir"]
    elif adr_dir_file is not None:
        directory = adr_dir_file.parent / adr_dir_file.read_text(encoding="utf-8").strip()
    else:
        directory = (root or cwd) / "docs" / "adr"
    directory = directory.resolve()
    template = (base / table["template"]) if "template" in table else directory / ".template.md"
    return Location(directory, root, template.resolve())


def no_dir(loc: Location) -> AdrError:
    return AdrError(
        "no-adr-dir", f"no ADR directory at {loc.dir}; run `adr init`", dir=str(loc.dir)
    )


def parse_all(items: Iterable[tuple[Path, str]]) -> AdrSet:
    adrs: list[Adr] = []
    problems: list[Finding] = []
    numbers: set[int] = set()
    for path, text in items:
        name = path.name
        if name.startswith(".") or name == "README.md":
            continue
        match = FILENAME_RE.match(name)
        if not match:
            problems.append(
                Finding("bad-filename", "warning", str(path), f"{name}: not NNNN-slug.md, ignored")
            )
            continue
        numbers.add(int(match[1]))
        try:
            adrs.append(parse_adr(path, text))
        except AdrError as exc:
            problems.append(Finding(exc.code, "error", str(path), exc.message))
    adrs.sort(key=lambda adr: (adr.number, adr.slug))
    return AdrSet(adrs, problems, numbers)


def _read(path: Path) -> str:
    if path.name.startswith(".") or not FILENAME_RE.match(path.name):
        return ""  # ignored or warned about by parse_all; never read
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""  # parses as no-frontmatter


def load(loc: Location) -> AdrSet:
    if not loc.dir.is_dir():
        raise no_dir(loc)
    paths = sorted(p for p in loc.dir.iterdir() if p.is_file())
    return parse_all((p, _read(p)) for p in paths)


def resolve(adrs: list[Adr], ref: str) -> Adr:
    ref = ref.strip()
    if not ref:
        raise AdrError("not-found", "empty ADR reference", ref=ref)
    if ref.isascii() and ref.isdigit():
        hits = [adr for adr in adrs if adr.number == int(ref)]
    else:
        hits = [adr for adr in adrs if ref.lower() in adr.slug]
    if not hits:
        raise AdrError("not-found", f"no ADR matches {ref!r}", ref=ref)
    if len(hits) > 1:
        names = [adr.path.name for adr in hits]
        raise AdrError(
            "ambiguous", f"{ref!r} matches {', '.join(names)}", ref=ref, candidates=names
        )
    return hits[0]


def atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        if path.exists():
            shutil.copymode(path, tmp)
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save(adr: Adr) -> None:
    adr.text = render(adr.meta, adr.body)
    atomic_write(adr.path, adr.text)


def set_relation(adr: Adr, name: str, numbers: Iterable[int]) -> None:
    values = sorted(set(numbers))
    adr.relations[name] = values
    if values:
        adr.meta[name] = flow(values)
    else:
        adr.meta.pop(name, None)


def set_status(adr: Adr, status: Status, today: dt.date) -> None:
    adr.status = status
    adr.date = today
    adr.meta["status"] = status.value
    adr.meta["date"] = today


def transition(adr: Adr, to: Status, *, force: bool = False, today: dt.date) -> None:
    if not force and (adr.status, to) not in TRANSITIONS:
        raise AdrError(
            "invalid-transition",
            f"{adr.id}: cannot change status from {adr.status} to {to} (use --force to repair)",
            current=adr.status.value,
            requested=to.value,
        )
    set_status(adr, to, today)


def slugify(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-") or "untitled"


def data_text(name: str) -> str:
    return (files("adrinaline") / "data" / name).read_text(encoding="utf-8")


def template_text(loc: Location) -> str:
    if loc.template.is_file():
        return loc.template.read_text(encoding="utf-8")
    return data_text("template.md")


def render_new(
    template: str,
    title: str,
    status: Status,
    today: dt.date,
    body: str | None,
    tags: list[str],
) -> str:
    try:
        meta, template_body = split(template.replace("{title}", title))
    except FrontmatterError as exc:
        raise AdrError("bad-template", f"template: {exc}") from exc
    meta["status"] = status.value
    meta["date"] = today
    if tags:
        old = meta.get("tags", [])
        old = [old] if isinstance(old, str) else old
        meta["tags"] = flow(sorted({*old, *tags}))
    if body is not None:
        template_body = f"# {title}\n\n{body.strip()}\n"
    return render(meta, template_body)


def numbers_in(directory: Path) -> set[int]:
    return {int(m[1]) for p in directory.iterdir() if (m := FILENAME_RE.match(p.name))}


def next_number(loc: Location) -> tuple[int, dict[int, str]]:
    return max(numbers_in(loc.dir), default=0) + 1, {}


def create_file(directory: Path, number: int, slug: str, text: str) -> Path:
    while True:
        if not any(directory.glob(f"{number:04d}-*.md")):
            path = directory / f"{number:04d}-{slug}.md"
            try:
                with path.open("x", encoding="utf-8", newline="") as handle:
                    handle.write(text)
                return path
            except FileExistsError:
                pass
        number += 1


def _cycle_error(relation: str, cycle: list[int]) -> AdrError:
    path = " -> ".join(f"{n:04d}" for n in cycle)
    return AdrError("cycle", f"this would create a {relation} cycle: {path}", cycle=cycle)


def supersede(graph: AdrGraph, old: Adr, new: Adr, *, force: bool, today: dt.date) -> None:
    if old.number == new.number:
        raise AdrError("self-relation", f"{old.id} cannot supersede itself")
    if old.status is not Status.ACCEPTED and not force:
        raise AdrError(
            "invalid-transition",
            f"{old.id} is {old.status}; only accepted ADRs can be superseded "
            "(use --force to repair)",
            current=old.status.value,
            requested=Status.SUPERSEDED.value,
        )
    if cycle := graph.cycle("supersedes", Edge(new.number, old.number, "supersedes")):
        raise _cycle_error("supersedes", cycle)
    set_relation(new, "supersedes", [*new.relations["supersedes"], old.number])
    set_relation(old, "superseded-by", [*old.relations["superseded-by"], new.number])
    set_status(old, Status.SUPERSEDED, today)
    save(new)
    save(old)


def link(graph: AdrGraph, src: Adr, relation: str, dst: Adr) -> bool:
    if relation not in LINKABLE:
        raise AdrError("bad-relation", f"cannot link with {relation!r}; use one of {LINKABLE}")
    if src.number == dst.number:
        raise AdrError("self-relation", f"{src.id} cannot {relation} itself")
    if relation in ACYCLIC and (
        cycle := graph.cycle(relation, Edge(src.number, dst.number, relation))
    ):
        raise _cycle_error(relation, cycle)
    if dst.number in src.relations[relation]:
        return False
    if relation == "relates-to" and src.number in dst.relations["relates-to"]:
        return False
    set_relation(src, relation, [*src.relations[relation], dst.number])
    save(src)
    return True


def unlink(src: Adr, relation: str, dst: Adr) -> list[Adr]:
    changed = []
    pairs = [(src, dst), (dst, src)] if relation == "relates-to" else [(src, dst)]
    for holder, target in pairs:
        if target.number in holder.relations[relation]:
            set_relation(
                holder, relation, [n for n in holder.relations[relation] if n != target.number]
            )
            save(holder)
            changed.append(holder)
    return changed
