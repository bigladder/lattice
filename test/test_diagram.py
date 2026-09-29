from lattice.docs.diagram import build_data_group_tree, render_tree

_SCHEMA = {
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


def test_build_data_group_tree_marks_required_and_optional_children():
    tree = build_data_group_tree(_SCHEMA, "Root")
    assert tree["name"] == "Root"
    names = {child["name"] for child in tree["subcategories"]}
    assert names == {"Required", "Optional*"}


def test_build_data_group_tree_ignores_scalar_fields():
    tree = build_data_group_tree(_SCHEMA, "Root")
    names = {child["name"] for child in tree["subcategories"]}
    assert "scalar_field" not in names


def test_build_data_group_tree_points_a_self_reference_back_at_its_own_node():
    tree = build_data_group_tree(_SCHEMA, "Optional")
    assert tree["name"] == "Optional"
    (child,) = tree["subcategories"]
    assert child == {"name": "Optional*", "recursive_target_path": ["Optional"]}


def test_build_data_group_tree_treats_undefined_group_as_leaf():
    """A Data Group referenced by Type but not defined in this schema file (e.g. a Standard 232
    common data group defined elsewhere) should render as a leaf, not raise."""
    schema = {
        "Root": {
            "Object Type": "Data Group",
            "Data Elements": {
                "metadata": {"Description": "d", "Type": "Group(Metadata)", "Required": True},
            },
        },
    }
    tree = build_data_group_tree(schema, "Root")
    (child,) = tree["subcategories"]
    assert child == {"name": "Metadata"}


def test_render_tree_produces_a_mermaid_fence():
    tree = build_data_group_tree(_SCHEMA, "Root")
    diagram = render_tree([tree])
    assert diagram.startswith("```mermaid\n")
    assert diagram.strip().endswith("```")
    assert "flowchart TD" in diagram
    assert '"Root"' in diagram
    assert '"Optional*"' in diagram


def test_render_tree_draws_a_self_reference_as_a_loop_not_a_new_box():
    tree = build_data_group_tree(_SCHEMA, "Root")
    diagram = render_tree([tree])
    # Exactly one box for "Optional*" -- the deeper, repeated occurrence loops back to it
    # instead of drawing a second box.
    assert diagram.count('"Optional*"') == 1
    assert "n_Root_Optional --> n_Root_Optional" in diagram


def test_render_tree_includes_caption_when_given():
    tree = build_data_group_tree(_SCHEMA, "Root")
    diagram = render_tree([tree], caption="A caption")
    assert diagram.startswith("**A caption**\n\n```mermaid\n")
