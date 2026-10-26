"""Split, parse and render Markdown files with YAML frontmatter (round-trip safe)."""

from collections.abc import Iterable
from io import StringIO

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError


class FrontmatterError(ValueError):
    """The file has no valid YAML frontmatter mapping."""


def _yaml() -> YAML:
    yaml = YAML()  # round-trip mode: keeps comments, key order and quoting
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def split(text: str) -> tuple[CommentedMap, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise FrontmatterError("missing frontmatter (file must start with '---')")
    for end, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            try:
                data = _yaml().load("".join(lines[1:end]))
            except YAMLError as exc:
                raise FrontmatterError(f"invalid YAML: {exc}") from exc
            if data is None:
                data = CommentedMap()
            if not isinstance(data, CommentedMap):
                raise FrontmatterError("frontmatter is not a mapping")
            # Store original values for comment column adjustment during render
            data._orig_values = {k: v for k, v in data.items()}  # type: ignore[attr-defined]
            return data, "".join(lines[end + 1 :])
    raise FrontmatterError("unterminated frontmatter (no closing '---')")


def render(meta: CommentedMap, body: str) -> str:
    if not meta:
        return f"---\n---\n{body}"

    # Adjust inline comment positions to preserve spacing when values change
    # When a value changes, we need to adjust the comment column to maintain spacing
    yaml_dump = _yaml()

    # Get original values if available
    orig_values = getattr(meta, "_orig_values", {})

    for key in meta:
        if key in meta.ca.items and meta.ca.items[key][2] is not None:
            # We have an inline comment for this key
            comment_token = meta.ca.items[key][2]
            orig_col = comment_token.column

            if key in orig_values and orig_values[key] != meta[key]:
                # Value was changed; adjust comment column to preserve spacing
                # Original spacing: orig_col - (len("key: ") + len(orig_value_rendered))
                # New column: (len("key: ") + len(new_value_rendered)) + original_spacing

                # For simplicity, calculate rendered lengths
                orig_val_str = _yaml_serialize(orig_values[key])
                new_val_str = _yaml_serialize(meta[key])

                # Calculate the adjusted column
                # Assume format: "key: value" (key + ": " + value)
                key_offset = len(key) + 2  # "key: "
                orig_spacing = orig_col - (key_offset + len(orig_val_str))
                new_col = key_offset + len(new_val_str) + orig_spacing
                comment_token.column = new_col

    buffer = StringIO()
    yaml_dump.dump(meta, buffer)
    return f"---\n{buffer.getvalue()}---\n{body}"


def _yaml_serialize(value):
    """Get the rendered YAML representation of a value."""
    buffer = StringIO()
    yaml_inst = _yaml()
    # Create a temporary map with just this value to get its rendering
    temp = CommentedMap({"_": value})
    yaml_inst.dump(temp, buffer)
    output = buffer.getvalue()
    # Extract just the value part (after "_: ")
    lines = output.split("\n")
    if lines and lines[0].startswith("_: "):
        return lines[0][3:].rstrip()
    return str(value)


def flow(items: Iterable) -> CommentedSeq:
    seq = CommentedSeq(items)
    seq.fa.set_flow_style()
    return seq
