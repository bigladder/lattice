import pathlib

import pytest

from lattice.file_io import dump
from lattice.meta_schema import generate_meta_schema, meta_validate_file


def _write_schema(tmp_path: pathlib.Path, custom_attribute: dict) -> pathlib.Path:
    schema_path = tmp_path / "CustomAttrTest.schema.yaml"
    dump(
        {
            "Schema": {"Object Type": "Meta", "Title": "t", "Description": "d", "Version": "0.1.0"},
            "MyAttribute": custom_attribute,
        },
        schema_path,
    )
    return schema_path


def _validate(tmp_path: pathlib.Path, schema_path: pathlib.Path) -> None:
    meta_schema_path = tmp_path / "CustomAttrTest.meta.schema.json"
    generate_meta_schema(meta_schema_path, schema_path)
    meta_validate_file(schema_path, meta_schema_path)


def test_well_formed_custom_attribute_passes_meta_schema_validation(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Object Type": "Custom Attribute",
            "Type": "Boolean",
            "Description": "A test attribute",
            "Applies To": ["Boolean"],
        },
    )
    _validate(tmp_path, schema_path)  # should not raise


def test_custom_attribute_missing_description_rejected(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Object Type": "Custom Attribute",
            "Type": "Boolean",
        },
    )
    with pytest.raises(Exception, match="Validation failed"):
        _validate(tmp_path, schema_path)


def test_custom_attribute_missing_type_rejected(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Object Type": "Custom Attribute",
            "Description": "A test attribute",
        },
    )
    with pytest.raises(Exception, match="Validation failed"):
        _validate(tmp_path, schema_path)


def test_custom_attribute_rejects_unknown_property(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Object Type": "Custom Attribute",
            "Type": "Boolean",
            "Description": "A test attribute",
            "Bogus Key": "not allowed",
        },
    )
    with pytest.raises(Exception, match="Validation failed"):
        _validate(tmp_path, schema_path)
