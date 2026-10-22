"""
Pin the current JSON Schema output so the generator can be rewritten against the Schema class
without changing what it produces.

Regenerate only when an output change is intended; that run fails every snapshot test by design, so
review the snapshot diff, then rerun without the variable:

    UPDATE_SNAPSHOTS=1 uv run pytest test/test_json_schema_snapshots.py       # POSIX shells
    $env:UPDATE_SNAPSHOTS=1; uv run pytest test/test_json_schema_snapshots.py  # PowerShell

PowerShell keeps the variable for the rest of the session; clear it with `Remove-Item Env:UPDATE_SNAPSHOTS`.

The snapshots follow examples/, which can change on main while this work lives on a long-lived
branch. After merging main, resolve any snapshot conflict or failure by regenerating with the
generator on this branch (never by hand-editing the JSON), in a commit of its own.
"""

import json
import os
import pathlib

import pytest

from lattice.file_io import dump, get_file_basename
from lattice.meta_schema import generate_meta_schema, meta_validate_file
from lattice.schema import Schema
from lattice.schema_to_json import JsonTranslator, generate_core_json_schema, generate_json_schema

UPDATE_SNAPSHOTS = os.environ.get("UPDATE_SNAPSHOTS") == "1"

TEST_DIRECTORY = pathlib.Path(__file__).parent
SNAPSHOT_DIRECTORY = TEST_DIRECTORY / "snapshots" / "json_schema"

# Set names double as snapshot subdirectories; prefixing examples keeps them from colliding with
# the core and features sets.
EXAMPLE_SCHEMA_DIRECTORIES = {
    f"examples/{path.parent.name}": path for path in sorted((TEST_DIRECTORY.parent / "examples").glob("*/schema"))
}
FEATURES_SET_NAME = "features"
CORE_SET_NAME = "core"


def _write_schema(directory: pathlib.Path, name: str, contents: dict) -> pathlib.Path:
    schema_path = directory / f"{name}.schema.yaml"
    dump(contents, schema_path)
    return schema_path


_FEATURES_SCHEMA: dict = {
    "Schema": {
        "Object Type": "Meta",
        "Title": "Features",
        "Description": "Exercises schema syntax the examples use rarely or not at all",
        "Version": "0.1.0",
        "Root Data Group": "Root",
    },
    # No Data Element uses this type: https://github.com/bigladder/lattice/issues/125
    "Identifier": {
        "Object Type": "String Type",
        "Description": "Upper-case identifier",
        "Regular Expression Pattern": "[A-Z]+",
        "Examples": ["ABC"],
    },
    "Kind": {
        "Object Type": "Enumeration",
        "Enumerators": {
            "KIND_A": {"Description": "First kind", "Display Text": "Kind A", "Notes": "Note about A"},
            "KIND_B": {"Description": "Second kind", "Display Text": "Kind B"},
        },
    },
    "Color": {
        "Object Type": "Enumeration",
        "Enumerators": {"RED": None, "GREEN": None},
    },
    "FirstAlternative": {
        "Object Type": "Data Group",
        "Data Elements": {
            "first_value": {"Description": "Value for the first alternative", "Type": "Numeric", "Units": "W"},
        },
    },
    "SecondAlternative": {
        "Object Type": "Data Group",
        "Data Elements": {
            "second_value": {"Description": "Value for the second alternative", "Type": "Integer"},
        },
    },
    "Statistics": {
        "Object Type": "Data Group",
        "Data Elements": {
            "kind": {"Description": "Selects the alternative", "Type": "<Kind>", "Required": True},
            "mean": {"Description": "Mean value, units supplied by the referencing element", "Type": "Numeric"},
            "detail": {
                "Description": "Alternative selected by kind",
                "Type": "Alternative(Group(FirstAlternative), Group(SecondAlternative))",
                "Constraints": "kind(KIND_A, KIND_B)",
            },
        },
    },
    "Node": {
        "Object Type": "Data Group",
        "Data Elements": {
            "name": {"Description": "Node name", "Type": "String", "Required": True, "ID": True},
            "children": {"Description": "Recursive children", "Type": "Array(Group(Node))"},
        },
    },
    "Root": {
        "Object Type": "Data Group",
        # The current generator hard-codes these spaced names, which can't be declared as Custom
        # Attribute objects: the meta-schema requires object names to be PascalCase.
        "Custom Attributes": ["Cycling Order", "Canonical End Uses"],
        "Data Elements": {
            "kind": {"Description": "Kind selector", "Type": "<Kind>", "Required": True},
            "flag": {"Description": "Boolean flag", "Type": "Boolean"},
            "count": {
                "Description": "Exclusive lower and upper bounds, multiple of two",
                "Type": "Integer",
                "Constraints": [">0", "<100", "%2"],
                "Notes": "Count notes",
            },
            "ratio": {
                "Description": "Inclusive bounds",
                "Type": "Numeric",
                "Units": "-",
                "Constraints": [">=0.0", "<=1.0"],
                "Cycling Order": 1,
            },
            "level": {"Description": "Value from a set", "Type": "Integer", "Constraints": "[1, 2, 3]"},
            "code": {"Description": "String with a pattern constraint", "Type": "String", "Constraints": '"[a-z]+"'},
            "pattern": {"Description": "Pattern type", "Type": "Pattern"},
            "colors": {
                "Description": "Array of enumerations with a closed length range",
                "Type": "Array(<Color>)",
                "Constraints": "[2..5]",
            },
            "exact_values": {
                "Description": "Array with an exact length",
                "Type": "Array(Numeric)",
                "Units": "m",
                "Constraints": "[3]",
            },
            "open_values": {
                "Description": "Array with an open-ended length range",
                "Type": "[Integer]",
                "Constraints": "[1..]",
                "Canonical End Uses": "heating, cooling",
            },
            "statistics": {
                "Description": "Shared group with nested attribute overrides and a pinned selector",
                "Type": "Group(Statistics)",
                "Constraints": "kind=KIND_A",
                "Nested Attribute Overrides": {
                    "Units": {"path": "mean", "value": "K"},
                    "Constraints": {"path": "mean", "value": ">0"},
                },
            },
            "nodes": {"Description": "Array of recursive groups", "Type": "Array(Group(Node))"},
            "node_reference": {"Description": "Reference to a node", "Type": "Reference(Group(Node))"},
            "if_defined": {"Description": "Required if flag is defined", "Type": "String", "Required": "if flag"},
            # Conditioned on `code`, not `flag`: the current generator crashes when one element is the
            # condition of both an "if x" and an "if !x" requirement
            # (https://github.com/bigladder/lattice/issues/126).
            "if_not_defined": {
                "Description": "Required if code is not defined",
                "Type": "String",
                "Required": "if !code",
            },
            "if_equal": {"Description": "Required if kind is KIND_A", "Type": "String", "Required": "if kind=KIND_A"},
            "if_not_equal": {
                "Description": "Required if kind is not KIND_A",
                "Type": "String",
                "Required": "if kind!=KIND_A",
            },
            "if_also_equal": {
                "Description": "Shares a condition with if_equal",
                "Type": "String",
                "Required": "if kind=KIND_A",
            },
            "if_boolean": {"Description": "Required if flag is True", "Type": "String", "Required": "if flag=True"},
            "if_both": {
                "Description": "Required if flag is defined and kind is KIND_B",
                "Type": "String",
                "Required": "if flag and kind=KIND_B",
            },
            "if_contains": {
                "Description": "Required if colors contains RED",
                "Type": "String",
                "Required": "if colors contains(RED)",
            },
        },
    },
}


def _snapshot_cases() -> list[tuple[str, str, str]]:
    # "unresolved" is each file's translation before $ref inlining, i.e. the per-file map that
    # generate_json_schema builds internally; "resolved" is its final output. Core is pinned once;
    # test_core_output_does_not_depend_on_schema_directory checks that once is enough.
    cases = [(CORE_SET_NAME, "unresolved", "core")]
    sets = [
        (set_name, [get_file_basename(path, depth=2) for path in sorted(directory.glob("*.schema.yaml"))])
        for set_name, directory in EXAMPLE_SCHEMA_DIRECTORIES.items()
    ]
    for set_name, names in [*sets, (FEATURES_SET_NAME, ["Features"])]:
        cases += [(set_name, form, name) for name in names for form in ("unresolved", "resolved")]
    return cases


SNAPSHOT_CASES = _snapshot_cases()


def _snapshot_path(set_name: str, form: str, name: str) -> pathlib.Path:
    return SNAPSHOT_DIRECTORY / set_name / form / f"{name}.schema.json"


def _schema_directory(set_name: str, tmp_path: pathlib.Path) -> pathlib.Path:
    if set_name in EXAMPLE_SCHEMA_DIRECTORIES:
        return EXAMPLE_SCHEMA_DIRECTORIES[set_name]
    # generate_json_schema reads every file in the schema's directory, so keep it schema-only.
    directory = tmp_path / "schema"
    directory.mkdir()
    if set_name == FEATURES_SET_NAME:
        _write_schema(directory, "Features", _FEATURES_SCHEMA)
    return directory


def _generate(set_name: str, form: str, name: str, schema_directory: pathlib.Path, output_path: pathlib.Path) -> None:
    if set_name == CORE_SET_NAME:
        dump(generate_core_json_schema(schema_directory.absolute()), output_path)
        return
    schema_path = (schema_directory / f"{name}.schema.yaml").absolute()
    if form == "resolved":
        generate_json_schema(schema_path, output_path)
    else:
        dump(JsonTranslator(schema_path).schema, output_path)


def test_features_schema_is_valid(tmp_path):
    # Snapshots only mean something for input the lattice pipeline accepts, and the replacement
    # generator reads Schema objects, so the features schema must pass both.
    schema_path = _write_schema(tmp_path, "Features", _FEATURES_SCHEMA)
    meta_schema_path = tmp_path / "Features.meta.schema.json"
    generate_meta_schema(meta_schema_path, schema_path)
    meta_validate_file(schema_path, meta_schema_path)
    Schema(schema_path)


def test_core_output_does_not_depend_on_schema_directory(tmp_path):
    # generate_json_schema translates core with the schema's directory for forward declarations.
    try:
        expected = generate_core_json_schema(tmp_path)
    except (KeyError, RuntimeError) as error:
        pytest.fail(f"Core needs a schema directory to resolve forward declarations ({error}); pin it per set.")
    # Serialized, so key order counts here just as it does in the snapshot comparison.
    expected_text = json.dumps(expected)
    for schema_directory in EXAMPLE_SCHEMA_DIRECTORIES.values():
        assert json.dumps(generate_core_json_schema(schema_directory.absolute())) == expected_text, (
            f"Core output differs for {schema_directory}; pin it per set."
        )


@pytest.mark.parametrize("set_name, form, name", [pytest.param(*case, id="/".join(case)) for case in SNAPSHOT_CASES])
def test_json_schema_matches_snapshot(set_name, form, name, tmp_path):
    schema_directory = _schema_directory(set_name, tmp_path)
    snapshot_path = _snapshot_path(set_name, form, name)

    if UPDATE_SNAPSHOTS:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        _generate(set_name, form, name, schema_directory, snapshot_path)
        # Fail rather than pass or skip, so a run with the variable left set can never come out green.
        pytest.fail("Snapshot regenerated; review the diff, then rerun without UPDATE_SNAPSHOTS.")

    if not snapshot_path.exists():
        pytest.fail(f"No snapshot at {snapshot_path.relative_to(TEST_DIRECTORY)}; generate it with UPDATE_SNAPSHOTS=1.")

    output_path = tmp_path / f"{name}.schema.json"
    _generate(set_name, form, name, schema_directory, output_path)
    # Compare text read with universal newlines: pins key order and formatting too, ignores
    # platform line endings, and a failure diffs line by line.
    assert output_path.read_text(encoding="utf-8") == snapshot_path.read_text(encoding="utf-8")


def test_no_stale_snapshots():
    expected = {_snapshot_path(*case) for case in SNAPSHOT_CASES}
    stale = sorted(
        str(path.relative_to(TEST_DIRECTORY)) for path in SNAPSHOT_DIRECTORY.rglob("*.json") if path not in expected
    )
    assert not stale, f"Snapshots with no matching schema; delete them: {stale}"
