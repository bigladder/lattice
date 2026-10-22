import pathlib

import pytest

from lattice.file_io import dump
from lattice.schema import (
    ArrayLengthLimitsConstraint,
    Constraint,
    MultipleConstraint,
    RangeConstraint,
    Schema,
    SetConstraint,
    StringPatternConstraint,
)


def _write_schema(tmp_path: pathlib.Path, data_element: dict) -> pathlib.Path:
    schema_path = tmp_path / "Values.schema.yaml"
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
            "Root": {"Object Type": "Data Group", "Data Elements": {"value": data_element}},
        },
        schema_path,
    )
    return schema_path


def _constraint(tmp_path: pathlib.Path, data_type: str, constraint_text: str) -> Constraint:
    data_element = {"Description": "d", "Type": data_type, "Constraints": constraint_text}
    if "Numeric" in data_type:
        data_element["Units"] = "-"
    schema = Schema(_write_schema(tmp_path, data_element))
    (constraint,) = schema.data_groups["Root"].data_elements["value"].constraints
    return constraint


@pytest.mark.parametrize(
    ("data_type", "text", "operator", "value"),
    [
        ("Integer", ">0", ">", 0),
        ("Integer", ">=-5", ">=", -5),
        ("Numeric", "<0.5", "<", 0.5),
        ("Numeric", "<=1e3", "<=", 1000.0),
        ("Array(Numeric)", ">=1", ">=", 1),
    ],
)
def test_range_constraint_operator_and_value(tmp_path, data_type, text, operator, value):
    constraint = _constraint(tmp_path, data_type, text)
    assert isinstance(constraint, RangeConstraint)
    assert constraint.operator == operator
    assert constraint.value == value
    assert type(constraint.value) is type(value)


@pytest.mark.parametrize(("data_type", "text", "value"), [("Integer", "%2", 2), ("Numeric", "%0.25", 0.25)])
def test_multiple_constraint_value(tmp_path, data_type, text, value):
    constraint = _constraint(tmp_path, data_type, text)
    assert isinstance(constraint, MultipleConstraint)
    assert constraint.value == value
    assert type(constraint.value) is type(value)


@pytest.mark.parametrize(
    ("data_type", "text", "values"),
    [
        ("Integer", "[1, 2, 3]", [1, 2, 3]),
        ("Numeric", "[1.5,2]", [1.5, 2]),
        ("String", '["a, b", "c"]', ["a, b", "c"]),
        ("<Color>", "[RED, GREEN]", ["RED", "GREEN"]),
    ],
)
def test_set_constraint_values(tmp_path, data_type, text, values):
    constraint = _constraint(tmp_path, data_type, text)
    assert isinstance(constraint, SetConstraint)
    assert constraint.values == values
    assert [type(value) for value in constraint.values] == [type(value) for value in values]


@pytest.mark.parametrize(
    ("text", "minimum", "maximum"),
    [("[1..4]", 1, 4), ("[..4]", None, 4), ("[1..]", 1, None), ("[12]", 12, 12)],
)
def test_array_length_limits_constraint_minimum_and_maximum(tmp_path, text, minimum, maximum):
    constraint = _constraint(tmp_path, "Array(Numeric)", text)
    assert isinstance(constraint, ArrayLengthLimitsConstraint)
    assert (constraint.minimum, constraint.maximum) == (minimum, maximum)


@pytest.mark.parametrize(
    ("text", "regular_expression"),
    [('"[a-z]+"', "[a-z]+"), ('"say "hi""', 'say "hi"')],
)
def test_string_pattern_constraint_regular_expression(tmp_path, text, regular_expression):
    constraint = _constraint(tmp_path, "String", text)
    assert isinstance(constraint, StringPatternConstraint)
    assert constraint.regular_expression == regular_expression
