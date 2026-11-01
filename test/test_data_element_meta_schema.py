"""Data element descriptions are required by the generated draft-07 schema."""

import pytest

from lattice.docs.schema_table import create_table_from_list
from lattice.file_io import dump
from lattice.meta_schema import generate_meta_schema, meta_validate_file


def validate_element(tmp_path, element, template=False):
    schema = {
        "Schema": {"Object Type": "Meta", "Title": "t", "Description": "d", "Version": "0.1.0"},
        "Example": {"Object Type": "Data Group", "Data Elements": {"value": element}},
    }
    if template:
        schema["ExampleTemplate"] = {
            "Object Type": "Data Group Template",
            "Required Data Elements": {"value": {"Type": "Numeric"}},
        }
        schema["Example"]["Data Group Template"] = "ExampleTemplate"
    path = tmp_path / "Example.schema.yaml"
    meta_path = tmp_path / "Example.meta.schema.json"
    dump(schema, path)
    generate_meta_schema(meta_path, path)
    meta_validate_file(path, meta_path)


@pytest.mark.parametrize("template", [False, True])
@pytest.mark.parametrize(
    "element",
    [
        {"Type": "Numeric"},
        {"Description": "", "Type": "Numeric"},
        {"Description": "A value"},
    ],
)
def test_invalid_data_element_attributes_are_rejected(tmp_path, element, template):
    with pytest.raises(Exception, match="Validation failed"):
        validate_element(tmp_path, element, template)


@pytest.mark.parametrize("template", [False, True])
def test_valid_data_element_attributes_are_accepted(tmp_path, template):
    validate_element(tmp_path, {"Description": "A value", "Type": "Numeric", "Custom Label": "kept"}, template)


def test_empty_attribute_does_not_break_definition_list():
    output = create_table_from_list(
        ["Name", "Description", "Type"],
        [{"Name": "value", "Description": "", "Type": "Numeric"}],
    )
    assert "Description:" not in output
    assert "Type:" in output
    assert "Numeric" in output
