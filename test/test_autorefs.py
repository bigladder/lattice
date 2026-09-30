from lattice.docs.autorefs import ReferenceIndex, link_diagram_nodes, link_mentions, link_prose_mentions
from lattice.docs.process_template import make_add_data_model


def _write_schema(path, name, contents):
    (path / f"{name}.schema.yaml").write_text(contents)


def _base_schema_block(name):
    return f"Schema:\n  Object Type: Meta\n  Title: {name}\n  Description: d\n  Version: '0.1.0'\n"


def test_reference_index_resolves_unambiguous_name_from_any_source(tmp_path):
    _write_schema(
        tmp_path,
        "Alpha",
        _base_schema_block("Alpha")
        + "OnlyHere:\n  Object Type: Data Group\n  Data Elements:\n    a:\n      Description: d\n      Type: String\n",
    )
    index = ReferenceIndex(tmp_path)
    assert index.resolve("OnlyHere") == "alpha:only_here"
    assert index.resolve("OnlyHere", source="AnythingElse") == "alpha:only_here"


def test_reference_index_prefers_same_source_when_name_is_ambiguous(tmp_path):
    for source in ("Alpha", "Beta"):
        _write_schema(
            tmp_path,
            source,
            _base_schema_block(source) + "Description:\n  Object Type: Data Group\n  Data Elements:\n"
            "    a:\n      Description: d\n      Type: String\n",
        )
    index = ReferenceIndex(tmp_path)
    assert index.resolve("Description", source="Alpha") == "alpha:description"
    assert index.resolve("Description", source="Beta") == "beta:description"
    # Asked from neither of the defining sources, an ambiguous name can't be resolved safely.
    assert index.resolve("Description", source="Gamma") is None
    assert index.resolve("Description") is None


def test_link_mentions_links_a_bare_name_and_skips_code_and_existing_links(tmp_path):
    _write_schema(
        tmp_path,
        "Alpha",
        _base_schema_block("Alpha")
        + "Target:\n  Object Type: Data Group\n  Data Elements:\n    a:\n      Description: d\n      Type: String\n",
    )
    index = ReferenceIndex(tmp_path)
    assert link_mentions("See Target for details.", index, source="Alpha") == (
        "See [`Target`][alpha:target] for details."
    )
    assert link_mentions("`Target` is already code.", index, source="Alpha") == "`Target` is already code."
    assert link_mentions("[Target](already-a-link)", index, source="Alpha") == "[Target](already-a-link)"


def test_link_mentions_links_a_self_reference_too(tmp_path):
    _write_schema(
        tmp_path,
        "Alpha",
        _base_schema_block("Alpha") + "Recursive:\n  Object Type: Data Group\n  Data Elements:\n"
        "    child:\n      Description: d\n      Type: Group(Recursive)\n",
    )
    index = ReferenceIndex(tmp_path)
    result = link_mentions("Recursive mentions itself.", index, source="Alpha")
    assert result == "[`Recursive`][alpha:recursive] mentions itself."


def test_type_column_links_referenced_group_and_stays_a_valid_grid_table(tmp_path):
    _write_schema(
        tmp_path,
        "Alpha",
        _base_schema_block("Alpha") + "Sample:\n  Object Type: Data Group\n  Data Elements:\n"
        "    child:\n      Description: d\n      Type: Group(Child)\n      Required: True\n"
        "Child:\n  Object Type: Data Group\n  Data Elements:\n    name:\n      Description: d\n      Type: String\n",
    )
    add_data_model = make_add_data_model(tmp_path, error_log=[])
    result = add_data_model("Alpha", base_level=1)

    assert "## Child {: #alpha:child }" in result
    assert "`Group(`[`Child`][alpha:child]`)`" in result

    lines = result.splitlines()
    border_width = None
    for line in lines:
        if line.startswith("+"):
            border_width = len(line)
        elif line.startswith("|"):
            assert len(line) == border_width


def test_reference_syntax_expands_and_links_like_group_syntax(tmp_path):
    _write_schema(
        tmp_path,
        "Alpha",
        _base_schema_block("Alpha") + "Sample:\n  Object Type: Data Group\n  Data Elements:\n"
        '    child_id:\n      Description: d\n      Type: ":Child:"\n'
        "Child:\n  Object Type: Data Group\n  Data Elements:\n    name:\n      Description: d\n      Type: String\n",
    )
    add_data_model = make_add_data_model(tmp_path, error_log=[])
    result = add_data_model("Alpha", base_level=1)
    assert "`Reference(Group(`[`Child`][alpha:child]`))`" in result


def test_link_prose_mentions_skips_grid_table_lines_and_link_definitions(tmp_path):
    _write_schema(
        tmp_path,
        "Alpha",
        _base_schema_block("Alpha")
        + "Target:\n  Object Type: Data Group\n  Data Elements:\n    a:\n      Description: d\n      Type: String\n",
    )
    index = ReferenceIndex(tmp_path)
    markdown = "See Target in prose.\n| Target | more |\n+--------+------+\n[1]: assets/Target.schema.json\n"
    result = link_prose_mentions(markdown, index, source="Alpha")
    lines = result.splitlines()
    assert lines[0] == "See [`Target`][alpha:target] in prose."
    assert lines[1] == "| Target | more |"
    assert lines[2] == "+--------+------+"
    assert lines[3] == "[1]: assets/Target.schema.json"


def test_link_prose_mentions_links_a_self_reference_but_not_the_heading_itself(tmp_path):
    _write_schema(
        tmp_path,
        "Alpha",
        _base_schema_block("Alpha")
        + "Target:\n  Object Type: Data Group\n  Data Elements:\n    a:\n      Description: d\n      Type: String\n",
    )
    index = ReferenceIndex(tmp_path)
    markdown = "## Target {: #alpha:target }\n\nTarget describes itself here.\n"
    result = link_prose_mentions(markdown, index, source="Alpha")
    lines = result.splitlines()
    assert lines[0] == "## Target {: #alpha:target }"
    assert lines[2] == "[`Target`][alpha:target] describes itself here."


def test_link_diagram_nodes_links_same_page_and_cross_page_targets(tmp_path):
    _write_schema(
        tmp_path,
        "Alpha",
        _base_schema_block("Alpha")
        + "Local:\n  Object Type: Data Group\n  Data Elements:\n    a:\n      Description: d\n      Type: String\n",
    )
    _write_schema(
        tmp_path,
        "Beta",
        _base_schema_block("Beta")
        + "Remote:\n  Object Type: Data Group\n  Data Elements:\n    a:\n      Description: d\n      Type: String\n",
    )
    index = ReferenceIndex(tmp_path)
    markdown = (
        "```mermaid\n"
        "flowchart TD\n"
        '    n_Local["Local"]\n'
        '    n_Local --> n_Local_Remote["Remote*"]\n'
        '    n_Local --> n_Local_Unknown["Unknown"]\n'
        "```\n"
    )
    result = link_diagram_nodes(markdown, index, source="Alpha")
    assert 'click n_Local "#alpha:local" "Local"' in result
    assert 'click n_Local_Remote "../Beta/#beta:remote" "Remote*"' in result
    assert "click n_Local_Unknown" not in result


def test_link_diagram_nodes_leaves_non_mermaid_content_untouched(tmp_path):
    _write_schema(
        tmp_path,
        "Alpha",
        _base_schema_block("Alpha")
        + "Local:\n  Object Type: Data Group\n  Data Elements:\n    a:\n      Description: d\n      Type: String\n",
    )
    index = ReferenceIndex(tmp_path)
    markdown = "Just prose mentioning Local, not inside a diagram.\n"
    assert link_diagram_nodes(markdown, index, source="Alpha") == markdown
