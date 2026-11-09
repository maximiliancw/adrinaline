"""Locate the ADR directory, load ADRs, resolve references and write files."""

import datetime as dt
import difflib
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
    STORED_RELATIONS,
    TRANSITIONS,
    Adr,
    AdrError,
    Finding,
    Status,
    parse_adr,
)


@dataclass(frozen=True)
class Location:
    """Where ADRs live: `dir`, git toplevel `root` (None outside git), `template`, and the
    `drift-commits` threshold from config (0 turns `stale-decision` off)."""

    dir: Path
    root: Path | None
    template: Path
    drift_commits: int = 0


@dataclass
class AdrSet:
    """Parsed ADRs sorted by (number, slug), the findings for files that did not parse, and every
    number seen in a valid filename (including files that failed to parse)."""

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
        table = _toml(pyproject).get("tool", {}).get("adrinaline")
        if table is not None and not isinstance(table, dict):
            raise AdrError("bad-config", f"{pyproject}: [tool.adrinaline] must be a table")
        return table
    return None


def locate(cwd: Path, env: Mapping[str, str], explicit: Path | None = None) -> Location:
    """Find the ADR directory. First hit wins: `explicit` (--dir), `ADR_DIR`, config `dir`,
    `.adr-dir`, then `<git root or cwd>/docs/adr`.

    Config is the nearest `.adrinaline.toml` or `pyproject.toml` with `[tool.adrinaline]`, searched
    from `cwd` up to the git root; its paths are relative to the file. `--dir` and `ADR_DIR` are
    relative to `cwd`. Raises `bad-config` for an unreadable or mistyped config.
    """
    root = git.toplevel(cwd)
    table: dict = {}
    base = cwd
    for directory in _ancestors(cwd, root):
        found = _config_table(directory)
        if found is not None:
            table, base = found, directory
            break
    adr_dir_file = next(
        (d / ".adr-dir" for d in _ancestors(cwd, root) if (d / ".adr-dir").is_file()), None
    )
    for key in ("dir", "template"):
        if key in table and not isinstance(table[key], str):
            raise AdrError("bad-config", f"config key {key!r} must be a string")
    drift_commits = table.get("drift-commits", 0)
    if isinstance(drift_commits, bool) or not isinstance(drift_commits, int) or drift_commits < 0:
        raise AdrError("bad-config", "config key 'drift-commits' must be a non-negative integer")
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
    return Location(directory, root, template.resolve(), drift_commits)


def no_dir(loc: Location) -> AdrError:
    return AdrError(
        "no-adr-dir", f"no ADR directory at {loc.dir}; run `adr init`", dir=str(loc.dir)
    )


def parse_all(items: Iterable[tuple[Path, str]]) -> AdrSet:
    """Parse `(path, text)` pairs. Dotfiles and `README.md` are skipped silently; other names that
    are not `NNNN-slug.md` give a `bad-filename` warning; a parse error becomes an error finding.
    """
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


def load(loc: Location, at: str | None = None) -> AdrSet:
    """Read and parse the ADR directory, or its state at git revision `at`.

    Raises `no-adr-dir` when the directory is missing.
    """
    if at is not None:
        return parse_all(git.read_dir_at(loc.root, at, loc.dir))
    if not loc.dir.is_dir():
        raise no_dir(loc)
    paths = sorted(p for p in loc.dir.iterdir() if p.is_file())
    return parse_all((p, _read(p)) for p in paths)


def resolve(adrs: list[Adr], ref: str) -> Adr:
    """Find the one ADR a reference names. All digits match the number; anything else is
    slugified (`Use PostgreSQL` is `use-postgresql`) and matches an exact slug, else a slug that
    contains it.

    Raises `not-found` (with close matches as candidates) or `ambiguous`.
    """
    ref = ref.strip()
    if not ref:
        raise AdrError("not-found", "empty ADR reference", ref=ref)
    if ref.isascii() and ref.isdigit():
        hits = [adr for adr in adrs if adr.number == int(ref)]
    else:
        needle = _slug(ref)  # "Use PostgreSQL" == use-postgresql
        hits = [adr for adr in adrs if adr.slug == needle] or [
            adr for adr in adrs if needle and needle in adr.slug
        ]
    if not hits:
        by_slug = {a.slug: a.path.name for a in reversed(adrs)}  # first file per slug wins
        names = [by_slug[s] for s in difflib.get_close_matches(_slug(ref), by_slug, n=3)]
        hint = f"; did you mean {', '.join(n.removesuffix('.md') for n in names)}?" if names else ""
        raise AdrError("not-found", f"no ADR matches {ref!r}{hint}", ref=ref, candidates=names)
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
    """Set the status and reset `date` to `today`, in memory only; the caller saves."""
    adr.status = status
    adr.date = today
    adr.meta["status"] = status.value
    adr.meta["date"] = today


def record_review(adr: Adr, today: dt.date, until: dt.date | None) -> None:
    adr.reviewed = today
    adr.meta["reviewed"] = today
    if until is not None:
        adr.review_by = until
        adr.meta["review-by"] = until


def transition(adr: Adr, to: Status, *, force: bool = False, today: dt.date) -> None:
    """`set_status` (so `date` is reset) if `TRANSITIONS` allows it or `force`, else raise
    `invalid-transition`. Does not save."""
    if not force and (adr.status, to) not in TRANSITIONS:
        raise AdrError(
            "invalid-transition",
            f"{adr.id}: cannot change status from {adr.status} to {to} (use --force to repair)",
            current=adr.status.value,
            requested=to.value,
        )
    set_status(adr, to, today)


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def slugify(title: str) -> str:
    return _slug(title) or "untitled"


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
    scope: list[str],
    review_by: dt.date | None = None,
) -> str:
    try:
        meta, template_body = split(template.replace("{title}", title))
    except FrontmatterError as exc:
        raise AdrError("bad-template", f"template: {exc}") from exc
    meta["status"] = status.value
    meta["date"] = today
    if tags:
        old = meta.get("tags") or []
        old = [old] if isinstance(old, str) else old
        if not isinstance(old, list) or not all(isinstance(t, str) for t in old):
            raise AdrError("bad-template", "template: tags must be a list of strings")
        meta["tags"] = flow(sorted({*old, *tags}))
    if scope:
        meta["scope"] = flow(list(dict.fromkeys(scope)))
    if review_by is not None:
        meta["review-by"] = review_by
    if body is not None:
        template_body = f"# {title}\n\n{body.strip()}\n"
    text = render(meta, template_body)
    try:  # validate before anything is written
        parse_adr(Path("0000-new.md"), text)
    except AdrError as exc:
        reason = exc.message.removeprefix("0000-new.md: ")
        raise AdrError("bad-template", f"template: {reason}") from exc
    return text


def numbers_in(directory: Path) -> set[int]:
    return {int(m[1]) for p in directory.iterdir() if (m := FILENAME_RE.match(p.name))}


def next_number(loc: Location) -> tuple[int, dict[int, str]]:
    """The next free number and the numbers it skipped.

    One more than the highest number in the directory or on any other branch or remote-tracking
    ref; `skipped` maps numbers above the local maximum that another ref already holds to that
    ref. A misnamed `NNNN-*.md` file also holds its number.
    """
    top = max(numbers_in(loc.dir), default=0)
    remote = git.numbers_on_refs(loc.root, loc.dir) if loc.root else {}
    skipped = {n: ref for n, ref in remote.items() if n > top}
    number = max([top, *skipped]) + 1
    while _taken(loc.dir, number):  # a misnamed NNNN-*.md file holds its number too
        number += 1
    return number, skipped


def _taken(directory: Path, number: int) -> bool:
    return any(directory.glob(f"{number:04d}-*.md"))


def create_file(directory: Path, number: int, slug: str, text: str) -> Path:
    while True:
        if _taken(directory, number):
            number += 1
            continue
        path = directory / f"{number:04d}-{slug}.md"
        try:
            # Reserve the number with O_EXCL first
            tmp = directory / f".{number:04d}.tmp"
            tmp.touch(exist_ok=False)
        except FileExistsError:
            # Race: another process took this number
            number += 1
            continue
        try:
            # Now write atomically to the final path
            atomic_write(path, text)
            return path
        finally:
            tmp.unlink(missing_ok=True)


def check_acyclic(graph: AdrGraph, relation: str, src: int, dst: int) -> None:
    if relation in ACYCLIC and (cycle := graph.cycle(relation, Edge(src, dst, relation))):
        path = " -> ".join(f"{n:04d}" for n in cycle)
        raise AdrError("cycle", f"this would create a {relation} cycle: {path}", cycle=cycle)


def supersede(graph: AdrGraph, old: Adr, new: Adr, *, force: bool, today: dt.date) -> None:
    """Make `new` supersede `old`: update both relation lists, set `old` to superseded (its
    `date` is reset) and write both files.

    Raises `self-relation`, `invalid-transition` (`old` is not accepted, unless `force`) or `cycle`.
    """
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
    check_acyclic(graph, "supersedes", new.number, old.number)
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
    check_acyclic(graph, relation, src.number, dst.number)
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


def renumber(s: AdrSet, adr: Adr, to: int) -> tuple[Path, list[Adr]]:
    """Rename `adr` to number `to`; return the new path and the other ADRs rewritten.

    Relations in other ADRs that point at the old number are rewritten, and `NNNN-slug.md` links
    in every body are updated. If the old number is shared by several ADRs, the numeric relations
    are left alone (they cannot tell which file is meant) and only the filename links change.
    Raises `exists` if `to` is taken.
    """
    if to in s.numbers:
        raise AdrError("exists", f"{to:04d} is already taken", number=to)
    old_name = adr.path.name
    new_path = adr.path.with_name(f"{to:04d}-{adr.slug}.md")
    unique = sum(1 for a in s.adrs if a.number == adr.number) == 1
    changed: list[Adr] = []
    for other in s.adrs:
        touched = False
        if unique and other is not adr:
            for name in STORED_RELATIONS:
                if adr.number in other.relations[name]:
                    set_relation(
                        other, name, [to if n == adr.number else n for n in other.relations[name]]
                    )
                    touched = True
        if old_name in other.body:
            other.body = other.body.replace(old_name, new_path.name)
            touched = True
        if touched and other is not adr:
            save(other)
            changed.append(other)
    atomic_write(new_path, render(adr.meta, adr.body))
    adr.path.unlink()
    return new_path, changed
