from lattice.docs.grid_table import visual_length, write_table


def test_visual_length_strips_non_rendering_markdown_syntax():
    assert visual_length("`code`") == len("code")
    assert visual_length("[text][ref]") == len("text")
    assert visual_length("[text](url)") == len("text")
    assert visual_length("**bold**") == len("bold")
    assert visual_length("m^2^") == len("m2")
    assert visual_length("plain text") == len("plain text")


def _assert_valid_grid_table(table_markdown):
    lines = [line for line in table_markdown.splitlines() if line]
    border_width = None
    for line in lines:
        if line.startswith("+"):
            border_width = len(line)
        elif line.startswith("|"):
            assert border_width is not None
            assert len(line) == border_width, f"misaligned row: {line!r}"


def test_table_with_heavy_link_syntax_stays_a_valid_rectangle():
    # A short, plain cell next to a cell that's almost entirely non-rendering syntax (link
    # brackets/reference id, code-span backticks): visual_length would badly underestimate this
    # column's real width if the real-length floor weren't applied on top of it.
    data = {
        "Name": ["short", "linked"],
        "Attributes": [
            "plain text",
            "`Enumeration(` [`AVeryLongEnumerationNameIndeed`][some_schema:a_very_long_enumeration_name_indeed] `)`",
        ],
    }
    table = write_table(data, ["Name", "Attributes"])
    _assert_valid_grid_table(table)


def test_table_with_multiline_fenced_block_stays_a_valid_rectangle():
    data = {
        "Name": ["a"],
        "Attributes": ["```\n- name: Lighting\n  subcategories:\n  - name: Interior Lighting\n```"],
    }
    table = write_table(data, ["Name", "Attributes"])
    _assert_valid_grid_table(table)
