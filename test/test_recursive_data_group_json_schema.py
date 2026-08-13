import pathlib

from lattice.file_io import dump, load
from lattice.schema_to_json import generate_json_schema


def _write_schema(tmp_path: pathlib.Path, name: str, contents: dict) -> pathlib.Path:
    schema_path = tmp_path / f"{name}.schema.yaml"
    dump(contents, schema_path)
    return schema_path


def test_self_referencing_data_group_terminates_and_validates_arbitrary_depth(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        "Recursive",
        {
            "Schema": {"Object Type": "Meta", "Title": "t", "Description": "d", "Version": "0.1.0"},
            "EndUse": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "name": {"Description": "d", "Type": "String", "Required": True},
                    "subcategories": {"Description": "d", "Type": "Array(Group(EndUse))"},
                },
            },
            "Root": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "end_uses": {"Description": "d", "Type": "Array(Group(EndUse))", "Required": True},
                },
            },
        },
    )
    output_path = tmp_path / "Recursive.schema.json"

    generate_json_schema(schema_path, output_path)  # should not RecursionError

    json_schema = load(output_path)
    end_use_items = json_schema["definitions"]["Root"]["properties"]["end_uses"]["items"]
    # However many concrete levels got unrolled, it must eventually fall back to a $ref
    # rather than an unbounded/failed expansion.
    node = end_use_items
    for _ in range(20):
        if "$ref" in node:
            break
        node = node["properties"]["subcategories"]["items"]
    else:
        raise AssertionError("Expected a $ref within 20 levels of unrolling")
    assert node["$ref"].endswith("#/definitions/EndUse")

    # An instance deeper than whatever got unrolled must still validate, proving the $ref
    # fallback -- not just the unrolled prefix -- actually works.
    deep_instance = {"end_uses": [{"name": "L1"}]}
    node = deep_instance["end_uses"][0]
    for i in range(2, 10):
        node["subcategories"] = [{"name": f"L{i}"}]
        node = node["subcategories"][0]

    from lattice.schema_to_json import validate_file

    instance_path = tmp_path / "deep.json"
    dump(deep_instance, instance_path)
    validate_file(instance_path, output_path)  # should not raise


def test_non_recursive_reference_chain_still_fully_resolves(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        "Chain",
        {
            "Schema": {"Object Type": "Meta", "Title": "t", "Description": "d", "Version": "0.1.0"},
            "C": {
                "Object Type": "Data Group",
                "Data Elements": {"value": {"Description": "d", "Type": "String", "Required": True}},
            },
            "B": {
                "Object Type": "Data Group",
                "Data Elements": {"c": {"Description": "d", "Type": "Group(C)", "Required": True}},
            },
            "A": {
                "Object Type": "Data Group",
                "Data Elements": {"b": {"Description": "d", "Type": "Group(B)", "Required": True}},
            },
        },
    )
    output_path = tmp_path / "Chain.schema.json"

    generate_json_schema(schema_path, output_path)

    json_schema = load(output_path)
    # A multi-hop, non-recursive chain (A -> B -> C) should fully inline: no leftover $ref.
    b_prop = json_schema["definitions"]["A"]["properties"]["b"]
    assert "$ref" not in b_prop
    c_prop = b_prop["properties"]["c"]
    assert "$ref" not in c_prop
    assert "value" in c_prop["properties"]
