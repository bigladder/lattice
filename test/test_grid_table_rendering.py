"""
Render generated grid tables the way the site does and check the HTML, not just the table's
shape: a line break Lattice adds only to fit a column must never change what a cell means.
"""

import html
import re

import markdown
import pytest

from lattice.docs.grid_table import write_table
from lattice.docs.mkdocs_web import markdown_extensions
from lattice.docs.schema_table import _format_custom_attribute_values, compress_list, create_table_from_list

# Enough leading words to move the wrap point across every position in a column.
WORDS_BEFORE = range(40)


def render(text):
    names, configs = [], {}
    for extension in markdown_extensions():
        if isinstance(extension, dict):
            ((name, config),) = extension.items()
            configs[name] = config
        else:
            name = extension
        names.append(name)
    return markdown.markdown(text, extensions=names, extension_configs=configs)


def render_cell(cell_text):
    return render(write_table({"Name": ["x"], "Attributes": [cell_text]}, ["Name", "Attributes"]))


def visible_text(rendered):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", rendered)).split())


def prose_around(phrase, words_before):
    return " ".join(["word"] * words_before + [phrase, "and", "then", "more", "words"])


def test_each_constraint_renders_as_its_own_bullet():
    element = {
        "Name": "ground_albedo",
        "Description": "Ground albedo",
        "Type": "{TimeSeries}",
        "Constraints": ['`display_name="Ground albedo"`', '`units="-"`', "`value_type=INSTANTANEOUS`"],
    }
    compress_list(element, "Constraints")
    rendered = render(create_table_from_list(["Name", "Description", "Type", "Constraints"], [element], level=0))
    assert rendered.count("<li>") == 3
    # Description, Type, and Constraints stay three separate terms instead of merging.
    assert rendered.count("<dt>") == 3


# Each starts a block (list, heading, quote, definition, table, reference, rule) when it begins
# a line, so a wrap must never leave one at the start of a continuation line.
BLOCK_MARKERS = ["-", "+", "*", "1.", "#", ">", ":", "|", "[1]:", "***", "==="]


@pytest.mark.parametrize("marker", BLOCK_MARKERS)
def test_wrapping_never_turns_prose_into_a_block(marker):
    phrase = f"Albedo {marker} Ground"
    for words_before in WORDS_BEFORE:
        rendered = render_cell(prose_around(phrase, words_before))
        assert not re.search(r"<(ul|ol|h\d|blockquote|dl|hr)\b", rendered), (marker, words_before)
        assert rendered.count("<table") == 1, (marker, words_before)
        assert phrase in visible_text(rendered), (marker, words_before)


def test_a_code_span_containing_spaces_is_never_split():
    for words_before in WORDS_BEFORE:
        rendered = render_cell(prose_around('`display_name="Albedo - Ground"`', words_before))
        assert '<code>display_name="Albedo - Ground"</code>' in rendered, words_before


def cell_html(rendered_table):
    return re.findall(r'<td colspan="1" rowspan="1">(.*?)</td>', rendered_table, re.S)[-1]


def normalized(fragment):
    return re.sub(r">\s+<", "><", " ".join(fragment.split()))


def long_cells(words_before):
    """Cells long enough to wrap, in the shapes Lattice writes them (see create_table_from_list)."""
    yield from (prose_around(f"Albedo {marker} Ground", words_before) for marker in BLOCK_MARKERS)
    yield prose_around('`display_name="Albedo - Ground"`', words_before)
    yield (
        f"Description:\n\n:   {prose_around('Ground albedo', words_before)}\n\n"
        f'Constraints:\n\n:   - `display_name="Ground albedo"` {prose_around("- note", words_before)}\n'
        '    - `units="-"`\n'
        "    - `value_type=INSTANTANEOUS`"
    )


def test_a_wrapped_cell_renders_the_same_as_its_text_outside_a_table():
    # Whatever the wrap points, a cell must mean what its text means on its own: this catches any
    # break that changes the Markdown, including syntax no other test here names.
    for words_before in WORDS_BEFORE:
        for cell_text in long_cells(words_before):
            in_table = cell_html(render_cell(cell_text))
            assert normalized(in_table) == normalized(render(cell_text)), (words_before, cell_text)


def test_link_buttons_keep_their_attribute_lists_when_wrapped():
    # The Examples page's Download column (see MkDocsWeb.make_examples_page).
    formats = ["YAML", "JSON", "CBOR"]
    buttons = "<br>".join(f"[{fmt}][{i}]{{: .md-button .md-button--small }}" for i, fmt in enumerate(formats, 1))
    table = write_table(
        {"File Name": ["example"], "Description": [prose_around("a long description", 30)], "Download": [buttons]},
        ["File Name", "Description", "Download"],
    )
    references = "\n".join(f"[{i}]: example.{fmt.lower()}" for i, fmt in enumerate(formats, 1))
    rendered = render(f"{table}\n{references}\n")
    assert rendered.count('class="md-button md-button--small"') == len(formats)


def test_a_fenced_block_in_a_cell_keeps_its_lines():
    element = {
        "Name": "end_uses",
        "Description": "End uses",
        "Canonical End Uses": [{"name": "Lighting", "subcategories": [{"name": "Interior Lighting"}]}],
    }
    _format_custom_attribute_values(element)
    rendered = render(create_table_from_list(["Name", "Description", "Canonical End Uses"], [element], level=0))
    code = html.unescape(re.search(r"<code>(.*?)</code></pre>", rendered, re.S).group(1))
    assert "- name: Lighting\n" in code
    assert "subcategories:\n" in code
