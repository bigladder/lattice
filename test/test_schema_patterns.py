# Needed for python versions < 3.9. 3.8 reaches end-of-life 2024-10.
from typing import List

import lattice.schema


def execute_pattern_test(
    pattern: lattice.schema.RegularExpressionPattern,
    valid_examples: List[str],
    invalid_examples: List[str],
    anchored: bool = True,
) -> None:
    pattern_text = pattern.anchored() if anchored else pattern.pattern

    for test in valid_examples:
        if not pattern.match(test, anchored):
            raise Exception(f'"{test}" does not match: {pattern_text}')

    for test in invalid_examples:
        if pattern.match(test, anchored):
            raise Exception(f'"{test}" matches: {pattern_text}')


def test_integer_pattern():
    execute_pattern_test(
        pattern=lattice.schema.IntegerType.value_pattern,
        valid_examples=[
            "1",
            "0",
            "-1",
            "+1",
            "+0",
            "-0",
            "999999",
            "-999999",
        ],
        invalid_examples=["0.5", "a", "1.0", "-9999.0"],
    )


def test_data_type_pattern():
    execute_pattern_test(
        pattern=lattice.schema.SchemaPatterns().data_types,
        valid_examples=[
            "Numeric",
            "[Numeric]",
            "{DataGroup}",
        ],
        invalid_examples=["Wrong", "[String][1..]", "ID"],
    )


def test_enumerator_pattern():
    execute_pattern_test(
        pattern=lattice.schema.EnumerationType.value_pattern,
        valid_examples=[
            "ENUMERATOR",
            "ENUMERATOR_2",
            "NEW_ENUMERATOR",
            "A",
        ],
        invalid_examples=["Wrong", "wrong", "_A", "A_", "000_A"],
        anchored=True,
    )


def test_value_pattern():
    execute_pattern_test(
        pattern=lattice.schema._value_pattern,
        valid_examples=[
            "3.14",
            '""',
            '"String"',
            "RightOh",
            "True",
            "False",
            "ENUMERATOR",
            "ENUMERATOR_2",
            "NEW_ENUMERATOR",
        ],
        invalid_examples=["true", "false"],
        anchored=True,
    )


def test_data_element_value_constraint_pattern():
    execute_pattern_test(
        pattern=lattice.schema.DataElementValueConstraint.pattern,
        valid_examples=["schema=RS0001"],
        invalid_examples=["Wrong", "data_element=wronG"],
        anchored=True,
    )


def test_selector_constraint_pattern():
    execute_pattern_test(
        pattern=lattice.schema.SelectorConstraint.pattern,
        valid_examples=["operation_speed_control_type(CONTINUOUS, DISCRETE)"],
        invalid_examples=[],
        anchored=True,
    )


def test_string_pattern_constraint_pattern():
    execute_pattern_test(
        pattern=lattice.schema.StringPatternConstraint.pattern,
        valid_examples=['"[A-Z]{2}"'],
        invalid_examples=["[A-Z]{2}"],
        anchored=True,
    )
