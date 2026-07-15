import pathlib

from lattice.docs.process_template import make_add_schema_table


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
