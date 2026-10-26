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
from adrinaline.graph import (
    FORWARD,
    IMPACT,
    AdrGraph,
    all_nodes,
    graph_data,
    render_dot,
    render_mermaid,
    render_text,
)
from adrinaline.model import LINKABLE, Adr, AdrError, Status
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


def non_negative(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return n


def cmd_new(ctx: Ctx) -> None:
    args, loc = ctx.args, ctx.loc
    if not loc.dir.is_dir():
        raise repo.no_dir(loc)
    wanted = {r: getattr(args, r.replace("-", "_")) for r in ("supersedes", *LINKABLE)}
    targets: dict[str, list[Adr]] = {}
    if any(wanted.values()):
        adrs = ctx.load().adrs
        targets = {
            r: list({a.number: a for a in (repo.resolve(adrs, ref) for ref in refs)}.values())
            for r, refs in wanted.items()
        }
        for old in targets["supersedes"]:
            if old.status is not Status.ACCEPTED and not args.force:
                raise AdrError(
                    "invalid-transition",
                    f"{old.id} is {old.status}; only accepted ADRs can be superseded",
                    current=old.status.value,
                    requested=Status.SUPERSEDED.value,
                )
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
    if targets:
        adrs = ctx.load().adrs
        by_path = {a.path: a for a in adrs}
        graph = AdrGraph(adrs)
        new = by_path[path]
        for old in targets["supersedes"]:
            repo.supersede(graph, by_path[old.path], new, force=args.force, today=today())
        for relation in LINKABLE:
            for dst in targets[relation]:
                repo.link(graph, new, relation, by_path[dst.path])
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
    graph = AdrGraph(adrs)
    relations = graph.related(adr.number)
    extra = {}
    if relations.get("superseded-by"):
        extra["successor"] = graph.successor(adr.number)
    ctx.out.result(
        adr_dict(adr, ctx.out, relations=relations, body=True, **extra),
        show_text(adr, relations, graph.nodes, ctx.out),
    )


def cmd_supersede(ctx: Ctx) -> None:
    adrs = ctx.load().adrs
    old, new = repo.resolve(adrs, ctx.args.old), repo.resolve(adrs, ctx.args.by)
    repo.supersede(AdrGraph(adrs), old, new, force=ctx.args.force, today=today())
    ctx.out.result(
        {"superseded": adr_dict(old, ctx.out), "by": adr_dict(new, ctx.out)},
        f"{old.id} {old.title}: superseded by {new.id} {new.title}",
    )


def cmd_link(ctx: Ctx) -> None:
    adrs = ctx.load().adrs
    src, dst = repo.resolve(adrs, ctx.args.src), repo.resolve(adrs, ctx.args.dst)
    changed = repo.link(AdrGraph(adrs), src, ctx.args.relation, dst)
    verb = "linked" if changed else "already linked"
    ctx.out.result(
        {"changed": [ctx.out.rel(src.path)] if changed else []},
        f"{verb}: {src.id} {ctx.args.relation} {dst.id}",
    )


def cmd_unlink(ctx: Ctx) -> None:
    adrs = ctx.load().adrs
    src, dst = repo.resolve(adrs, ctx.args.src), repo.resolve(adrs, ctx.args.dst)
    changed = repo.unlink(src, ctx.args.relation, dst)
    text = "\n".join(f"updated {ctx.out.rel(a.path)}" for a in changed) or "no such link"
    ctx.out.result({"changed": [ctx.out.rel(a.path) for a in changed]}, text)


def cmd_log(ctx: Ctx) -> None:
    adr = repo.resolve(ctx.load().adrs, ctx.args.ref)
    rows = git.log(ctx.loc.root, adr.path)
    text = "\n".join(f"{r['date']}  {r['commit'][:8]}  {r['author']}  {r['subject']}" for r in rows)
    ctx.out.result(rows, text or "no commits yet")


def cmd_graph(ctx: Ctx) -> None:
    args = ctx.args
    graph = AdrGraph(ctx.load().adrs)
    relations = tuple(args.relation) if args.relation else (IMPACT if args.reverse else FORWARD)
    sub = None
    if args.ref is not None:
        start = repo.resolve(graph.adrs, args.ref).number
        sub = graph.reachable(start, relations, reverse=args.reverse, depth=args.depth)
        nodes, edges = sub.nodes, sub.edges
    else:
        edges = [e for e in graph.edges if e.relation in relations]
        nodes = all_nodes(graph)
    fmt = "json" if args.json else args.format
    if fmt == "json":
        ctx.out.json_mode = True
        ctx.out.result(graph_data(graph, nodes, edges), "")
    elif fmt == "mermaid":
        ctx.out.result(None, render_mermaid(graph, nodes, edges))
    elif fmt == "dot":
        ctx.out.result(None, render_dot(graph, nodes, edges))
    else:
        ctx.out.result(None, render_text(graph, sub, edges))


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


def cmd_renumber(ctx: Ctx) -> None:
    s = ctx.load()
    adr = repo.resolve(s.adrs, ctx.args.ref)
    old = ctx.out.rel(adr.path)
    new_path, changed = repo.renumber(s, adr, ctx.args.to)
    updated = [ctx.out.rel(a.path) for a in changed]
    lines = [f"renamed {old} -> {ctx.out.rel(new_path)}", *(f"updated {p}" for p in updated)]
    ctx.out.result({"from": old, "to": ctx.out.rel(new_path), "updated": updated}, "\n".join(lines))


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
    for relation in ("supersedes", *LINKABLE):
        p.add_argument(f"--{relation}", action="append", default=[], metavar="REF")
    p.add_argument("--force", action="store_true", help="supersede ADRs that are not accepted")

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

    p = add("supersede", cmd_supersede, "mark OLD as superseded by NEW")
    p.add_argument("old", metavar="OLD")
    p.add_argument("--by", required=True, metavar="NEW")
    p.add_argument("--force", action="store_true", help="supersede even if OLD is not accepted")

    for name, func, help_ in (
        ("link", cmd_link, "add a relation"),
        ("unlink", cmd_unlink, "remove a relation"),
    ):
        p = add(name, func, help_)
        p.add_argument("src", metavar="REF")
        p.add_argument("relation", choices=LINKABLE)
        p.add_argument("dst", metavar="REF")

    p = add("graph", cmd_graph, "render the ADR graph")
    p.add_argument("ref", nargs="?")
    p.add_argument("--relation", action="append", choices=FORWARD)
    p.add_argument("--depth", type=non_negative)
    p.add_argument("--reverse", action="store_true", help="follow inverse edges (impact)")
    p.add_argument("--format", choices=("text", "mermaid", "dot", "json"), default="text")

    p = add("renumber", cmd_renumber, "give an ADR a new number and update references")
    p.add_argument("ref")
    p.add_argument("--to", type=int, required=True, metavar="N")

    p = add("log", cmd_log, "show the git history of an ADR")
    p.add_argument("ref")

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
