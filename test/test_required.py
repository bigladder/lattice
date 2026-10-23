import pathlib
import re

import pytest

from lattice.file_io import dump
from lattice.schema import Condition, Schema


def _write_schema(tmp_path: pathlib.Path, value_required) -> pathlib.Path:
    schema_path = tmp_path / "Required.schema.yaml"
    dump(
        {
            "Schema": {
                "Object Type": "Meta",
                "Title": "t",
                "Description": "d",
                "Version": "0.1.0",
                "Root Data Group": "Root",
            },
            "Color": {"Object Type": "Enumeration", "Enumerators": {"RED": None, "GREEN": None}},
            "Root": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "name": {"Description": "d", "Type": "String", "Required": True},
                    "flag": {"Description": "d", "Type": "Boolean"},
                    "color": {"Description": "d", "Type": "<Color>"},
                    "count": {"Description": "d", "Type": "Integer"},
                    "ratio": {"Description": "d", "Type": "Numeric", "Units": "-"},
                    "label": {"Description": "d", "Type": "String"},
                    "code_pattern": {"Description": "d", "Type": "Pattern"},
                    "colors": {"Description": "d", "Type": "Array(<Color>)"},
                    "value": {"Description": "d", "Type": "String", "Required": value_required},
                },
            },
        },
        schema_path,
    )
    return schema_path


def _conditions(tmp_path: pathlib.Path, value_required: str) -> tuple:
    (requirement,) = Schema(_write_schema(tmp_path, value_required)).data_groups["Root"].conditional_requirements()
    assert requirement.data_element.name == "value"
    return requirement.conditions


@pytest.mark.parametrize(
    ("text", "condition"),
    [
        ("if flag", Condition("flag", "defined")),
        ("if !flag", Condition("flag", "defined", negated=True)),
        ("if flag=True", Condition("flag", "equals", True)),
        ("if flag=False", Condition("flag", "equals", False)),
        ("if color=RED", Condition("color", "equals", "RED")),
        ("if color!=RED", Condition("color", "equals", "RED", negated=True)),
        ("if count=3", Condition("count", "equals", 3)),
        ("if ratio=3", Condition("ratio", "equals", 3.0)),
        ('if label="a b"', Condition("label", "equals", "a b")),
        ('if label="salt and pepper"', Condition("label", "equals", "salt and pepper")),
        ('if code_pattern="[A-Z]+"', Condition("code_pattern", "equals", "[A-Z]+")),
        ("if colors contains(GREEN)", Condition("colors", "contains", "GREEN")),
    ],
)
def test_required_clause_is_parsed_into_a_condition(tmp_path, text, condition):
    (parsed,) = _conditions(tmp_path, text)
    assert parsed == condition
    assert type(parsed.value) is type(condition.value)


def test_required_clauses_joined_with_and_are_all_conditions(tmp_path):
    assert _conditions(tmp_path, "if flag and color=GREEN and !count") == (
        Condition("flag", "defined"),
        Condition("color", "equals", "GREEN"),
        Condition("count", "defined", negated=True),
    )


def test_and_inside_a_quoted_value_does_not_split_the_clause(tmp_path):
    assert _conditions(tmp_path, 'if label="a and b" and flag') == (
        Condition("label", "equals", "a and b"),
        Condition("flag", "defined"),
    )


@pytest.mark.parametrize("value_required", [True, False])
def test_unconditional_required_has_no_conditional_requirement(tmp_path, value_required):
    data_group = Schema(_write_schema(tmp_path, value_required)).data_groups["Root"]
    assert data_group.conditional_requirements() == []
    expected = ["name", "value"] if value_required else ["name"]
    assert [data_element.name for data_element in data_group.required_elements()] == expected


def test_conditionally_required_element_is_not_in_required_elements(tmp_path):
    data_group = Schema(_write_schema(tmp_path, "if flag")).data_groups["Root"]
    assert [data_element.name for data_element in data_group.required_elements()] == ["name"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("if missing", "refers to 'missing', which isn't a Data Element"),
        ("if count=1.5", "'1.5' is not a valid 'Integer' value"),
        ("if flag=RED", "'RED' is not a valid 'Boolean' value"),
        ('if color="RED"', "'\"RED\"' is not a valid '<Color>' value"),
        ("if label contains(RED)", "needs 'label' to be an Array"),
        ("if colors contains(1)", "'1' is not a valid '<Color>' value"),
        ("if color=BLUE", "uses 'BLUE', which isn't an enumerator of 'Color'"),
        ("if colors contains(BLUE)", "uses 'BLUE', which isn't an enumerator of 'Color'"),
        ("if flag or count", "isn't a recognized condition"),
        ("flag", "must be True, False or start with 'if '"),
    ],
)
def test_malformed_required_is_rejected(tmp_path, text, message):
    with pytest.raises(Exception, match=re.escape(message)):
        Schema(_write_schema(tmp_path, text))
