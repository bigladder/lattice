from lattice.docs.diagram import build_data_group_tree, render_tree
from lattice.file_io import dump
from lattice.schema import Schema

_META = {"Object Type": "Meta", "Title": "t", "Description": "d", "Version": "0.1.0"}

_SCHEMA = {
    "Schema": _META,
    "Root": {
        "Object Type": "Data Group",
        "Data Elements": {
            "required_child": {
                "Description": "d",
                "Type": "Group(Required)",
                "Required": True,
            },
            "optional_child": {
                "Description": "d",
                "Type": "Array(Group(Optional))",
            },
            "scalar_field": {
                "Description": "d",
                "Type": "String",
            },
        },
    },
    "Required": {
        "Object Type": "Data Group",
        "Data Elements": {
            "name": {"Description": "d", "Type": "String", "Required": True},
        },
    },
    "Optional": {
        "Object Type": "Data Group",
        "Data Elements": {
            "self_reference": {"Description": "d", "Type": "Array(Group(Optional))"},
        },
    },
}


def _write_schema(tmp_path, contents, name="Sample"):
    schema_path = tmp_path / f"{name}.schema.yaml"
    dump(contents, schema_path)
    return schema_path


def _sample_schema(tmp_path):
    return Schema(_write_schema(tmp_path, _SCHEMA))


def test_build_data_group_tree_marks_required_and_optional_children(tmp_path):
    tree = build_data_group_tree(_sample_schema(tmp_path).get_data_group("Root"))
    assert tree["name"] == "Root"
    names = {child["name"] for child in tree["subcategories"]}
    assert names == {"Required", "Optional*"}


def test_build_data_group_tree_ignores_scalar_fields(tmp_path):
    tree = build_data_group_tree(_sample_schema(tmp_path).get_data_group("Root"))
    names = {child["name"] for child in tree["subcategories"]}
    assert "scalar_field" not in names


def test_build_data_group_tree_points_a_self_reference_back_at_its_own_node(tmp_path):
    tree = build_data_group_tree(_sample_schema(tmp_path).get_data_group("Optional"))
    assert tree["name"] == "Optional"
    (child,) = tree["subcategories"]
    assert child == {"name": "Optional*", "recursive_target_path": ["Optional"]}


def test_build_data_group_tree_recurses_into_a_common_group_from_a_referenced_schema(tmp_path):
    """A Data Group referenced by Type but not defined in this schema file (e.g. a Standard 232
    common data group named in this schema's own Schema.References) is resolved via
    Schema.get_data_group and walked into just like a locally-defined one, including its own
    further children -- instead of stopping as a dead-end leaf."""
    _write_schema(
        tmp_path,
        {
            "Schema": {**_META, "References": ["Common"]},
            "Root": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "shared": {"Description": "d", "Type": "Group(Shared)", "Required": True},
                },
            },
        },
        name="Sample",
    )
    _write_schema(
        tmp_path,
        {
            "Schema": _META,
            "Shared": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "nested": {"Description": "d", "Type": "Group(Nested)", "Required": True},
                },
            },
            "Nested": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "name": {"Description": "d", "Type": "String", "Required": True},
                },
            },
        },
        name="Common",
    )
    schema = Schema(tmp_path / "Sample.schema.yaml")
    tree = build_data_group_tree(schema.get_data_group("Root"))
    (shared,) = tree["subcategories"]
    assert shared["name"] == "Shared"
    (nested,) = shared["subcategories"]
    assert nested == {"name": "Nested"}


def test_render_tree_produces_a_mermaid_fence(tmp_path):
    tree = build_data_group_tree(_sample_schema(tmp_path).get_data_group("Root"))
    diagram = render_tree([tree])
    assert diagram.startswith("```mermaid\n")
    assert diagram.strip().endswith("```")
    assert "flowchart TD" in diagram
    assert '"Root"' in diagram
    assert '"Optional*"' in diagram


def test_render_tree_draws_a_self_reference_as_a_loop_not_a_new_box(tmp_path):
    tree = build_data_group_tree(_sample_schema(tmp_path).get_data_group("Root"))
    diagram = render_tree([tree])
    # Exactly one box for "Optional*" -- the deeper, repeated occurrence loops back to it
    # instead of drawing a second box.
    assert diagram.count('"Optional*"') == 1
    assert "n_Root_Optional --> n_Root_Optional" in diagram


def test_render_tree_includes_caption_when_given(tmp_path):
    tree = build_data_group_tree(_sample_schema(tmp_path).get_data_group("Root"))
    diagram = render_tree([tree], caption="A caption")
    assert diagram.startswith("**A caption**\n\n```mermaid\n")
