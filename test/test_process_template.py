import pathlib

from lattice.docs.process_template import make_add_data_model, make_add_schema_diagram, make_add_schema_table
from lattice.file_io import dump

_META = {"Object Type": "Meta", "Title": "Sample", "Description": "d", "Version": "0.1.0"}


def test_add_schema_table_falls_back_to_core(tmp_path):
    """add_schema_table should resolve 'core' even when it is absent from schema_dir."""
    add_schema_table = make_add_schema_table(tmp_path)
    result = add_schema_table("core", "Metadata")
    assert "ERROR" not in result
    assert "schema_name" in result
    assert "author" in result


def test_add_schema_table_primary_dir_takes_precedence(tmp_path):
    """A schema file in the primary dir should be used before the lattice fallback."""
    schema_path = tmp_path / "core.schema.yaml"
    schema_path.write_text(
        "Schema:\n"
        "  Object Type: Meta\n"
        "  Title: Test\n"
        "  Description: test\n"
        "  Version: '0.1.0'\n"
        "SentinelGroup:\n"
        "  Object Type: Data Group\n"
        "  Data Elements:\n"
        "    sentinel_field:\n"
        "      Description: Only in override\n"
        "      Type: String\n"
    )
    add_schema_table = make_add_schema_table(tmp_path)
    result = add_schema_table("core", "SentinelGroup")
    assert "ERROR" not in result
    assert "sentinel_field" in result


def _write_sample_schema(tmp_path):
    schema_path = tmp_path / "Sample.schema.yaml"
    schema_path.write_text(
        "Schema:\n"
        "  Object Type: Meta\n"
        "  Title: Test\n"
        "  Description: test\n"
        "  Version: '0.1.0'\n"
        "Sample:\n"
        "  Object Type: Data Group\n"
        "  Data Elements:\n"
        "    child:\n"
        "      Description: d\n"
        "      Type: Group(Child)\n"
        "      Required: True\n"
        "Child:\n"
        "  Object Type: Data Group\n"
        "  Data Elements:\n"
        "    name:\n"
        "      Description: d\n"
        "      Type: String\n"
    )
    return schema_path


def test_add_schema_diagram_defaults_root_to_source(tmp_path):
    """A schema file's root Data Group is conventionally named the same as the file itself."""
    _write_sample_schema(tmp_path)
    add_schema_diagram = make_add_schema_diagram(tmp_path)
    result = add_schema_diagram("Sample")
    assert "ERROR" not in result
    assert '"Sample"' in result
    assert '"Child"' in result


def test_add_schema_diagram_accepts_an_explicit_root(tmp_path):
    _write_sample_schema(tmp_path)
    add_schema_diagram = make_add_schema_diagram(tmp_path)
    result = add_schema_diagram("Sample", root="Child")
    assert "ERROR" not in result
    assert '"Sample"' not in result
    assert '"Child"' in result


def test_add_schema_diagram_reports_an_unknown_root(tmp_path):
    _write_sample_schema(tmp_path)
    add_schema_diagram = make_add_schema_diagram(tmp_path)
    result = add_schema_diagram("Sample", root="Nonexistent")
    assert "ERROR" in result
    assert "Nonexistent" in result


def test_add_data_model_without_a_declared_root_keeps_file_order(tmp_path):
    """No 'Root Data Group' declared (e.g. a common-types-only schema like core): render exactly
    as before -- raw file order, no hierarchy walk, no common-Data-Group insertion."""
    schema_path = tmp_path / "Sample.schema.yaml"
    dump(
        {
            "Schema": _META,
            "Zebra": {"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
            "Apple": {"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
        },
        schema_path,
    )
    add_data_model = make_add_data_model(tmp_path, error_log=[])
    result = add_data_model("Sample", base_level=1)
    assert result.index("## Zebra") < result.index("## Apple")


def test_add_data_model_orders_data_groups_by_top_down_hierarchy(tmp_path):
    schema_path = tmp_path / "Sample.schema.yaml"
    dump(
        {
            "Schema": {**_META, "Root Data Group": "Root"},
            # Declared out of hierarchy order on purpose, to prove the output reorders them.
            "B": {"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
            "A": {"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
            "Root": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "a": {"Description": "d", "Type": "Group(A)", "Required": True},
                    "b": {"Description": "d", "Type": "Group(B)", "Required": True},
                },
            },
        },
        schema_path,
    )
    add_data_model = make_add_data_model(tmp_path, error_log=[])
    result = add_data_model("Sample", base_level=1)
    assert result.index("## Root") < result.index("## A") < result.index("## B")


def test_add_data_model_embeds_a_common_data_group_with_an_origin_note(tmp_path):
    schema_path = tmp_path / "Sample.schema.yaml"
    dump(
        {
            "Schema": {**_META, "Root Data Group": "Root", "References": ["Common"]},
            "Root": {
                "Object Type": "Data Group",
                "Data Elements": {"shared": {"Description": "d", "Type": "Group(Shared)", "Required": True}},
            },
        },
        schema_path,
    )
    dump(
        {
            "Schema": {"Object Type": "Meta", "Title": "Common", "Description": "d", "Version": "0.1.0"},
            "Shared": {"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
        },
        tmp_path / "Common.schema.yaml",
    )
    add_data_model = make_add_data_model(tmp_path, error_log=[])
    result = add_data_model("Sample", base_level=1)
    assert "## Shared" in result
    assert '_Defined in the "Common" schema._' in result


def test_add_data_model_cites_core_by_standard_name_not_its_title(tmp_path):
    """core is lattice's own built-in library of ASHRAE Standard 232 common types -- a reader
    wouldn't look it up by its file-level Title ("Core"), so the origin note names the standard
    it implements instead."""
    schema_path = tmp_path / "Sample.schema.yaml"
    dump(
        {
            "Schema": {**_META, "Root Data Group": "Root"},
            "Root": {
                "Object Type": "Data Group",
                "Data Elements": {"metadata": {"Description": "d", "Type": "Group(Metadata)", "Required": True}},
            },
        },
        schema_path,
    )
    add_data_model = make_add_data_model(tmp_path, error_log=[])
    result = add_data_model("Sample", base_level=1)
    assert "## Metadata" in result
    assert "_Defined in ANSI/ASHRAE/IBPSA Standard 232._" in result


def test_add_data_model_include_common_false_omits_the_common_data_group(tmp_path):
    schema_path = tmp_path / "Sample.schema.yaml"
    dump(
        {
            "Schema": {**_META, "Root Data Group": "Root", "References": ["Common"]},
            "Root": {
                "Object Type": "Data Group",
                "Data Elements": {"shared": {"Description": "d", "Type": "Group(Shared)", "Required": True}},
            },
        },
        schema_path,
    )
    dump(
        {
            "Schema": {"Object Type": "Meta", "Title": "Common", "Description": "d", "Version": "0.1.0"},
            "Shared": {"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
        },
        tmp_path / "Common.schema.yaml",
    )
    add_data_model = make_add_data_model(tmp_path, error_log=[])
    result = add_data_model("Sample", base_level=1, include_common=False)
    assert "## Shared" not in result
    assert "_Defined in the" not in result


def test_add_data_model_warns_about_and_drops_an_unreferenced_local_group(tmp_path):
    schema_path = tmp_path / "Sample.schema.yaml"
    dump(
        {
            "Schema": {**_META, "Root Data Group": "Root"},
            "Root": {
                "Object Type": "Data Group",
                "Data Elements": {"name": {"Description": "d", "Type": "String"}},
            },
            "Unreferenced": {
                "Object Type": "Data Group",
                "Data Elements": {"name": {"Description": "d", "Type": "String"}},
            },
        },
        schema_path,
    )
    error_log = []
    add_data_model = make_add_data_model(tmp_path, error_log=error_log)
    result = add_data_model("Sample", base_level=1)
    assert "## Unreferenced" not in result
    assert any("Unreferenced" in message for message in error_log)
