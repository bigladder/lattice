import pathlib

import pytest

from lattice.file_io import dump
from lattice.schema import Schema


def test_schema():
    schema = Schema(pathlib.Path("examples", "fan_spec", "schema", "RS0003.schema.yaml"))
    for data_group in schema.data_groups.values():
        print(f"\nData Group: {data_group.name}")
        for data_element in data_group.data_elements.values():
            print(f"  {data_element.name}")
            print(f"    {data_element.description}")
    for enumeration in schema.enumerations.values():
        print(f"\nEnumeration: {enumeration.name}")
        for enumerator in enumeration.enumerators.values():
            print(f"  {enumerator.name}")


def _write_schema(tmp_path: pathlib.Path, data_element: dict) -> pathlib.Path:
    schema_path = tmp_path / "Constrained.schema.yaml"
    dump(
        {
            "Schema": {"Object Type": "Meta", "Title": "t", "Description": "d", "Version": "0.1.0"},
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {"element": data_element},
            },
        },
        schema_path,
    )
    return schema_path


def test_constraint_rejected_for_inapplicable_data_type(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Description": "a string with a numeric range constraint",
            "Type": "String",
            "Constraints": ">=0.0",
        },
    )
    with pytest.raises(Exception, match="is not applicable to Data Type"):
        Schema(schema_path)


def test_constraint_allowed_for_applicable_data_type(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Description": "a numeric with a numeric range constraint",
            "Type": "Numeric",
            "Units": "-",
            "Constraints": ">=0.0",
        },
    )
    Schema(schema_path)


def test_array_length_constraint_checked_against_array_type(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Description": "an array of numerics with a length constraint",
            "Type": "[Numeric]",
            "Units": "-",
            "Constraints": ["[1..]"],
        },
    )
    Schema(schema_path)


def test_range_constraint_checked_against_array_element_type(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Description": "an array of strings with a numeric range constraint",
            "Type": "[String]",
            "Constraints": [">=0.0"],
        },
    )
    with pytest.raises(Exception, match="is not applicable to Data Type"):
        Schema(schema_path)


@pytest.mark.parametrize(
    ("data_type", "constraint"),
    [
        ("Numeric", '[0.0, 1.0, 2.0]'),
        ("Integer", "[0, 1, 2]"),
        ("String", '["A", "B"]'),
    ],
)
def test_set_constraint_allowed_for_plain_old_data_types(tmp_path, data_type, constraint):
    data_element = {
        "Description": "a plain-old-data element with a set constraint",
        "Type": data_type,
        "Constraints": constraint,
    }
    if data_type == "Numeric":
        data_element["Units"] = "-"
    schema_path = _write_schema(tmp_path, data_element)
    Schema(schema_path)


def test_set_constraint_rejected_for_data_group_type(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Description": "a data group with a set constraint",
            "Type": "{Metadata}",
            "Constraints": '["A", "B"]',
        },
    )
    with pytest.raises(Exception, match="is not applicable to Data Type"):
        Schema(schema_path)


def test_set_constraint_rejected_for_boolean_type(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Description": "a boolean with a set constraint",
            "Type": "Boolean",
            "Constraints": "[True]",
        },
    )
    with pytest.raises(Exception, match="is not applicable to Data Type"):
        Schema(schema_path)


def _write_multi_group_schema(tmp_path: pathlib.Path, groups: dict) -> pathlib.Path:
    schema_path = tmp_path / "MultiGroup.schema.yaml"
    dump(
        {
            "Schema": {
                "Object Type": "Meta",
                "Title": "t",
                "Description": "d",
                "Version": "0.1.0",
                "Root Data Group": "RootGroup",
            },
            **groups,
        },
        schema_path,
    )
    return schema_path


def test_data_element_value_constraint_resolves_against_array_element_type(tmp_path):
    schema_path = _write_multi_group_schema(
        tmp_path,
        {
            "Item": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "value": {"Description": "d", "Type": "Numeric", "Units": "-"},
                },
            },
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "items": {
                        "Description": "an array of Item groups",
                        "Type": "Array(Group(Item))",
                        "Constraints": ['value=0.0'],
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_data_element_value_constraint_rejected_for_array_of_non_data_group(tmp_path):
    schema_path = _write_multi_group_schema(
        tmp_path,
        {
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "values": {
                        "Description": "an array of numerics",
                        "Type": "Array(Numeric)",
                        "Units": "-",
                        "Constraints": ['value=0.0'],
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="is not applicable to Data Type"):
        Schema(schema_path)


def test_array_length_bare_integer_resolves_as_array_length_for_data_group_array(tmp_path):
    schema_path = _write_multi_group_schema(
        tmp_path,
        {
            "Item": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "value": {"Description": "d", "Type": "Numeric", "Units": "-"},
                },
            },
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "items": {
                        "Description": "an array of exactly 12 Item groups",
                        "Type": "Array(Group(Item))",
                        "Constraints": "[12]",
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_array_length_bare_integer_resolves_as_array_length_for_numeric_array(tmp_path):
    # Array(Numeric) is compatible with both Set (its element type, Numeric) and Array Length
    # Limits (the array itself); since the Data Element's own Type is an Array, Array Length
    # Limits should win.
    schema_path = _write_schema(
        tmp_path,
        {
            "Description": "an array of exactly 12 numeric values",
            "Type": "Array(Numeric)",
            "Units": "-",
            "Constraints": "[12]",
        },
    )
    Schema(schema_path)


def test_array_length_bare_integer_resolves_as_set_for_plain_numeric(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Description": "a numeric constrained to the single value 12",
            "Type": "Numeric",
            "Units": "-",
            "Constraints": "[12]",
        },
    )
    Schema(schema_path)
