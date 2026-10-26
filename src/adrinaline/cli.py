"""Command-line interface: argparse wiring and one cmd_<name> function per command."""

import argparse
import datetime as dt
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from adrinaline import __version__, git, repo
from adrinaline.check import run_checks
from adrinaline.frontmatter import render, split
from adrinaline.model import Adr, AdrError, Status
from adrinaline.output import EXIT_FINDINGS, EXIT_OK, Out, adr_dict, error

AGENT_HINT = "Agents: run `adr prime` first. Every command accepts --json."


@dataclass
class Ctx:
    args: argparse.Namespace
    loc: repo.Location
    out: Out
    cwd: Path

    def load(self) -> repo.AdrSet:
        return repo.load(self.loc)


def today() -> dt.date:
    return dt.date.today()


def list_line(adr: Adr) -> str:
    return f"{adr.id}  {adr.status:<10}  {adr.date}  {adr.title}"


def show_text(
    adr: Adr, relations: dict[str, list[int]], by_number: dict[int, Adr], out: Out
) -> str:
    lines = [f"{adr.id} {adr.title}", f"status: {adr.status}   date: {adr.date}"]
    if adr.tags:
        lines.append("tags: " + ", ".join(adr.tags))
    if adr.scope:
        lines.append("scope: " + ", ".join(adr.scope))
    for name, numbers in relations.items():
        labels = [
            f"{n:04d} {by_number[n].title}" if n in by_number else f"{n:04d} (missing)"
            for n in numbers
        ]
        lines.append(f"{name}: " + "; ".join(labels))
    lines += [f"path: {out.rel(adr.path)}", "", adr.body.strip()]
    return "\n".join(lines)


def cmd_init(ctx: Ctx) -> None:
    loc, force = ctx.loc, ctx.args.force
    loc.dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if force or not loc.template.exists():
        loc.template.parent.mkdir(parents=True, exist_ok=True)
        repo.atomic_write(loc.template, repo.data_text("template.md"))
        written.append(loc.template)
    first = next(loc.dir.glob("0001-*.md"), None)
    if force or first is None:
        target = first or loc.dir / "0001-record-architecture-decisions.md"
        meta, body = split(repo.data_text("0001.md"))
        meta["date"] = today()
        if name := git.user_name(ctx.cwd):
            meta["decision-makers"] = repo.flow([name])
        repo.atomic_write(target, render(meta, body))
        written.append(target)
    paths = [ctx.out.rel(p) for p in written]
    text = "\n".join(f"wrote {p}" for p in paths) or "already initialised"
    ctx.out.result({"dir": ctx.out.rel(loc.dir), "written": paths}, text)


def _edit(path: Path) -> None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    try:
        subprocess.run([*shlex.split(editor), str(path)], check=False)
    except OSError as exc:
        raise AdrError("io", f"cannot run editor {editor!r}: {exc}") from exc


def cmd_new(ctx: Ctx) -> None:
    args, loc = ctx.args, ctx.loc
    if not loc.dir.is_dir():
        raise repo.no_dir(loc)
    body = None
    if args.body_file == "-":
        body = sys.stdin.read()
    elif args.body_file:
        try:
            body = Path(args.body_file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AdrError("io", f"cannot read {args.body_file}: {exc}") from exc
    status = Status.ACCEPTED if args.accepted else Status.PROPOSED
    text = repo.render_new(repo.template_text(loc), args.title, status, today(), body, args.tag)
    number, skipped = repo.next_number(loc)
    path = repo.create_file(loc.dir, number, repo.slugify(args.title), text)
    for n, ref in sorted(skipped.items()):
        ctx.out.note(f"skipped {n:04d}, taken on {ref}")
    if args.edit:
        _edit(path)
    adr = repo.parse_adr(path, path.read_text(encoding="utf-8"))
    skipped_json = {f"{n:04d}": ref for n, ref in sorted(skipped.items())}
    ctx.out.result(adr_dict(adr, ctx.out, skipped=skipped_json), ctx.out.rel(path))


def cmd_show(ctx: Ctx) -> None:
    adrs = ctx.load().adrs
    adr = repo.resolve(adrs, ctx.args.ref)
    if ctx.args.raw:
        ctx.out.result({"path": ctx.out.rel(adr.path), "text": adr.text}, adr.text)
        return
    relations = {name: nums for name, nums in adr.relations.items() if nums}
    by_number = {a.number: a for a in adrs}
    ctx.out.result(
        adr_dict(adr, ctx.out, relations=relations, body=True),
        show_text(adr, relations, by_number, ctx.out),
    )


def cmd_list(ctx: Ctx) -> None:
    args = ctx.args
    adrs = [
        adr
        for adr in ctx.load().adrs
        if (not args.status or adr.status in args.status)
        and (not args.tag or set(args.tag) & set(adr.tags))
    ]
    ctx.out.result([adr_dict(a, ctx.out) for a in adrs], "\n".join(list_line(a) for a in adrs))


def cmd_index(ctx: Ctx) -> None:
    adrs = ctx.load().adrs
    rows = ["| ADR | Title | Status | Date |", "|---|---|---|---|"]
    rows += [
        f"| [{a.id}]({a.path.name}) | {a.title.replace('|', '\\|')} | {a.status} | {a.date} |"
        for a in adrs
    ]
    ctx.out.result([adr_dict(a, ctx.out) for a in adrs], "\n".join(rows))


def _set_status(to: Status) -> Callable[[Ctx], None]:
    def cmd(ctx: Ctx) -> None:
        adr = repo.resolve(ctx.load().adrs, ctx.args.ref)
        before = adr.status
        repo.transition(adr, to, force=ctx.args.force, today=today())
        repo.save(adr)
        ctx.out.result(adr_dict(adr, ctx.out), f"{adr.id} {adr.title}: {before} -> {to}")

    return cmd


def cmd_check(ctx: Ctx) -> int:
    findings = run_checks(ctx.load(), template_exists=ctx.loc.template.is_file())
    failed = any(f.severity == "error" for f in findings) or (ctx.args.strict and bool(findings))
    rows = [asdict(f) | {"path": ctx.out.rel(Path(f.path)) if f.path else ""} for f in findings]
    text = "\n".join(f"{r['severity']}: {r['code']}: {r['message']}" for r in rows) or "ok"
    ctx.out.result({"ok": not failed, "findings": rows}, text)
    return EXIT_FINDINGS if failed else EXIT_OK


def cmd_skill(ctx: Ctx) -> None:
    text = repo.data_text("SKILL.md")
    ctx.out.result({"skill": text}, text)


def build_parser() -> argparse.ArgumentParser:
    # Global flags work before and after the subcommand: the subparser copies use
    # SUPPRESS so they never overwrite a value given at the top level.
    common = argparse.ArgumentParser(add_help=False)
    parser = argparse.ArgumentParser(
        prog="adr", description="Git-native Architecture Decision Records.", epilog=AGENT_HINT
    )
    S = argparse.SUPPRESS
    for target, hidden in ((common, True), (parser, False)):
        target.add_argument(
            "--json",
            action="store_true",
            default=S if hidden else False,
            help="print JSON on stdout",
        )
        target.add_argument(
            "--dir",
            type=Path,
            default=S if hidden else None,
            help="ADR directory (overrides discovery)",
        )
        target.add_argument(
            "-q", "--quiet", action="store_true", default=S if hidden else False, help="no output"
        )
    parser.add_argument("--version", action="version", version=f"adr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def add(name: str, func: Callable[[Ctx], int | None], help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, parents=[common], help=help_, description=help_)
        p.set_defaults(func=func)
        return p

    p = add("init", cmd_init, "create the ADR directory, template and ADR 0001")
    p.add_argument("--force", action="store_true", help="overwrite the template and ADR 0001")

    p = add("new", cmd_new, "create a new ADR")
    p.add_argument("title")
    p.add_argument("--accepted", action="store_true", help="create as accepted")
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--body-file", metavar="PATH", help="body below the title ('-' = stdin)")
    p.add_argument("--edit", action="store_true", help="open $VISUAL/$EDITOR afterwards")

    p = add("show", cmd_show, "show one ADR")
    p.add_argument("ref")
    p.add_argument("--raw", action="store_true", help="print the file verbatim")

    p = add("list", cmd_list, "list ADRs")
    p.add_argument("--status", action="append", choices=[s.value for s in Status])
    p.add_argument("--tag", action="append")

    add("index", cmd_index, "print a Markdown index table")

    for name, to in (
        ("accept", Status.ACCEPTED),
        ("reject", Status.REJECTED),
        ("deprecate", Status.DEPRECATED),
    ):
        p = add(name, _set_status(to), f"mark an ADR as {to}")
        p.add_argument("ref")
        p.add_argument("--force", action="store_true", help="allow any transition (repairs)")

    p = add("check", cmd_check, "validate all ADRs")
    p.add_argument("--strict", action="store_true", help="fail on warnings too")

    add("skill", cmd_skill, "print the bundled agent skill (SKILL.md)")
    return parser


def main(
    argv: list[str] | None = None,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    cwd = (cwd or Path.cwd()).resolve()
    env = os.environ if env is None else env
    try:
        loc = repo.locate(cwd, env, args.dir)
        out = Out(json_mode=args.json, quiet=args.quiet, base=loc.root or cwd)
        return args.func(Ctx(args, loc, out, cwd)) or EXIT_OK
    except AdrError as exc:
        return error(exc, args.json)


def run() -> None:
    sys.exit(main())
