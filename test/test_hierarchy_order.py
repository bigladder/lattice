import pytest

from lattice.file_io import dump
from lattice.schema import Schema

_META = {"Object Type": "Meta", "Title": "t", "Description": "d", "Version": "0.1.0"}


def _write_schema(tmp_path, name, meta_overrides=None, **groups):
    schema_path = tmp_path / f"{name}.schema.yaml"
    dump({"Schema": {**_META, **(meta_overrides or {})}, **groups}, schema_path)
    return schema_path


def test_get_enumeration_resolves_locally(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        "Sample",
        Enum={"Object Type": "Enumeration", "Enumerators": {"A": {}}},
    )
    schema = Schema(schema_path)
    assert schema.get_enumeration("Enum").name == "Enum"


def test_get_enumeration_resolves_from_a_referenced_schema(tmp_path):
    _write_schema(
        tmp_path,
        "Sample",
        meta_overrides={"References": ["Common"]},
        Root={
            "Object Type": "Data Group",
            "Data Elements": {"kind": {"Description": "d", "Type": "<Kind>", "Required": True}},
        },
    )
    _write_schema(tmp_path, "Common", Kind={"Object Type": "Enumeration", "Enumerators": {"A": {}}})
    schema = Schema(tmp_path / "Sample.schema.yaml")
    enumeration = schema.get_enumeration("Kind")
    assert enumeration.name == "Kind"
    assert enumeration.parent_schema.name == "Common"


def test_get_enumeration_raises_when_not_found(tmp_path):
    schema_path = _write_schema(tmp_path, "Sample")
    schema = Schema(schema_path)
    with pytest.raises(Exception, match="not found"):
        schema.get_enumeration("Nonexistent")


def test_referenced_children_finds_group_and_enumeration_and_skips_scalars(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        "Sample",
        Kind={"Object Type": "Enumeration", "Enumerators": {"A": {}}},
        Child={"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
        Root={
            "Object Type": "Data Group",
            "Data Elements": {
                "child": {"Description": "d", "Type": "Group(Child)", "Required": True},
                "kind": {"Description": "d", "Type": "<Kind>"},
                "scalar": {"Description": "d", "Type": "String"},
            },
        },
    )
    schema = Schema(schema_path)
    children = schema.get_data_group("Root").referenced_children()
    names = {(element.name, type(child).__name__, child.name) for element, child in children}
    assert names == {("child", "DataGroup", "Child"), ("kind", "Enumeration", "Kind")}


def test_referenced_children_unwraps_array_and_alternative(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        "Sample",
        A={"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
        B={"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
        Root={
            "Object Type": "Data Group",
            "Data Elements": {
                "items": {"Description": "d", "Type": "Array(Group(A))"},
                "either": {"Description": "d", "Type": "Alternative(Group(A), Group(B))"},
            },
        },
    )
    schema = Schema(schema_path)
    children = schema.get_data_group("Root").referenced_children()
    found = [child.name for _element, child in children]
    assert found == ["A", "A", "B"]


def _write_root_and_child(tmp_path, root_elements, **extra_groups):
    return _write_schema(
        tmp_path,
        "Sample",
        meta_overrides={"Root Data Group": "Root"},
        Root={"Object Type": "Data Group", "Data Elements": root_elements},
        **extra_groups,
    )


def test_hierarchy_order_walks_depth_first_from_the_root(tmp_path):
    # Root -> A -> A1, Root -> B; depth-first should fully expand A (and A1) before B.
    schema_path = _write_root_and_child(
        tmp_path,
        {
            "a": {"Description": "d", "Type": "Group(A)", "Required": True},
            "b": {"Description": "d", "Type": "Group(B)", "Required": True},
        },
        A={
            "Object Type": "Data Group",
            "Data Elements": {"a1": {"Description": "d", "Type": "Group(A1)", "Required": True}},
        },
        A1={"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
        B={"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
    )
    schema = Schema(schema_path)
    ordered_groups, _ordered_enums, orphans, _orphan_enums = schema.hierarchy_order()
    assert [dg.name for dg in ordered_groups] == ["Root", "A", "A1", "B"]
    assert orphans == []


def test_hierarchy_order_lists_each_group_once_at_its_first_reference(tmp_path):
    # Both a1 and b reference Shared; it should appear once, at its first (a1's) position.
    schema_path = _write_root_and_child(
        tmp_path,
        {
            "a": {"Description": "d", "Type": "Group(A)", "Required": True},
            "b": {"Description": "d", "Type": "Group(Shared)", "Required": True},
        },
        A={
            "Object Type": "Data Group",
            "Data Elements": {"shared": {"Description": "d", "Type": "Group(Shared)", "Required": True}},
        },
        Shared={"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
    )
    schema = Schema(schema_path)
    ordered_groups, *_ = schema.hierarchy_order()
    assert [dg.name for dg in ordered_groups] == ["Root", "A", "Shared"]


def test_hierarchy_order_includes_a_common_group_from_a_referenced_schema(tmp_path):
    _write_root_and_child(
        tmp_path,
        {"metadata": {"Description": "d", "Type": "Group(Metadata)", "Required": True}},
    )
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
    _write_schema(
        tmp_path,
        "Common",
        Shared={"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
    )
    schema = Schema(schema_path)
    ordered_groups, _ordered_enums, orphans, _orphan_enums = schema.hierarchy_order()
    assert [dg.name for dg in ordered_groups] == ["Root", "Shared"]
    assert ordered_groups[1].parent_schema.name == "Common"
    assert orphans == []


def test_hierarchy_order_reports_a_locally_defined_group_never_referenced_as_an_orphan(tmp_path):
    schema_path = _write_root_and_child(
        tmp_path,
        {"name": {"Description": "d", "Type": "String"}},
        Unreferenced={"Object Type": "Data Group", "Data Elements": {"name": {"Description": "d", "Type": "String"}}},
    )
    schema = Schema(schema_path)
    ordered_groups, _ordered_enums, orphans, _orphan_enums = schema.hierarchy_order()
    assert [dg.name for dg in ordered_groups] == ["Root"]
    assert [dg.name for dg in orphans] == ["Unreferenced"]


def test_hierarchy_order_orders_enumerations_by_first_reference_too(tmp_path):
    schema_path = _write_root_and_child(
        tmp_path,
        {
            "a": {"Description": "d", "Type": "Group(A)", "Required": True},
            "kind": {"Description": "d", "Type": "<RootKind>"},
        },
        A={
            "Object Type": "Data Group",
            "Data Elements": {"kind": {"Description": "d", "Type": "<AKind>", "Required": True}},
        },
        RootKind={"Object Type": "Enumeration", "Enumerators": {"X": {}}},
        AKind={"Object Type": "Enumeration", "Enumerators": {"Y": {}}},
    )
    schema = Schema(schema_path)
    _ordered_groups, ordered_enums, _orphans, orphan_enums = schema.hierarchy_order()
    # Depth-first: Root's first Data Element ("a") is fully expanded -- including AKind, found
    # while inside A -- before the walk returns to Root's second Data Element ("kind").
    assert [en.name for en in ordered_enums] == ["AKind", "RootKind"]
    assert orphan_enums == []
