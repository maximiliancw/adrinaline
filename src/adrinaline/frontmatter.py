"""Split, parse and render Markdown files with YAML frontmatter (round-trip safe)."""

from collections.abc import Iterable
from io import StringIO

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError


class FrontmatterError(ValueError):
    """The file has no valid YAML frontmatter mapping."""


class FrontmatterMissing(FrontmatterError):
    """The file does not start with a frontmatter block."""


class FrontmatterDateError(FrontmatterError):
    """A date field in the frontmatter could not be parsed."""


def _yaml() -> YAML:
    yaml = YAML()  # round-trip mode: keeps comments, key order and quoting
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def split(text: str) -> tuple[CommentedMap, str]:
    """Split a file into its frontmatter mapping and the body after the closing `---`."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise FrontmatterMissing("missing frontmatter (file must start with '---')")
    for end, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            try:
                data = _yaml().load("".join(lines[1:end]))
            except ValueError as exc:
                raise FrontmatterDateError(f"invalid YAML: {exc}") from exc
            except YAMLError as exc:
                raise FrontmatterError(f"invalid YAML: {exc}") from exc
            if data is None:
                data = CommentedMap()
            if not isinstance(data, CommentedMap):
                raise FrontmatterError("frontmatter is not a mapping")
            return data, "".join(lines[end + 1 :])
    raise FrontmatterError("unterminated frontmatter (no closing '---')")


def render(meta: CommentedMap, body: str) -> str:
    """Inverse of `split`: comments, key order and quoting of `meta` survive."""
    if not meta:
        return f"---\n---\n{body}"
    buffer = StringIO()
    _yaml().dump(meta, buffer)
    return f"---\n{buffer.getvalue()}---\n{body}"


def flow(items: Iterable) -> CommentedSeq:
    """A list that renders in flow style (`[1, 2]`) instead of one item per line."""
    seq = CommentedSeq(items)
    seq.fa.set_flow_style()
    return seq
