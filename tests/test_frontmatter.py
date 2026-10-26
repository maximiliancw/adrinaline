import pytest

from adrinaline.frontmatter import FrontmatterError, flow, render, split

DOC = (
    "---\n"
    "status: accepted  # keep me\n"
    "date: 2026-01-15\n"
    "custom-key: [a, b]\n"
    "---\n"
    "# Title\n\nBody with\n---\na rule.\n"
)


def test_round_trip_is_byte_stable():
    meta, body = split(DOC)
    assert render(meta, body) == DOC


def test_body_rule_is_not_a_frontmatter_end():
    _, body = split(DOC)
    assert body == "# Title\n\nBody with\n---\na rule.\n"


def test_edit_keeps_comments_and_unknown_keys():
    meta, body = split(DOC)
    meta["status"] = "superseded"
    out = render(meta, body)
    assert "status: superseded  # keep me\n" in out
    assert "custom-key: [a, b]\n" in out


def test_flow_lists_render_inline():
    meta, body = split("---\nstatus: proposed\n---\n# T\n")
    meta["supersedes"] = flow([3, 1])
    assert "supersedes: [3, 1]\n" in render(meta, body)


def test_empty_frontmatter_is_an_empty_mapping():
    meta, body = split("---\n---\n# T\n")
    assert dict(meta) == {} and body == "# T\n"


@pytest.mark.parametrize(
    "text",
    [
        "# no frontmatter\n",
        "---\nstatus: x\n",
        "---\n- a list\n---\n# T\n",
        "---\nkey: [unclosed\n---\n# T\n",
    ],
)
def test_invalid_frontmatter_raises(text):
    with pytest.raises(FrontmatterError):
        split(text)
