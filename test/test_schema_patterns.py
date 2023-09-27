from lattice.schema import SchemaPatterns, RegularExpressionPattern


def execute_pattern_test(pattern: RegularExpressionPattern, valid_examples: list[str], invalid_examples: list[str], anchored: bool = True):

    pattern_text = pattern.anchored() if anchored else pattern.pattern

    for test in valid_examples:
        if not pattern.match(test, anchored):
            raise Exception(f"\"{test}\" does not match: {pattern_text}")

    for test in invalid_examples:
        if pattern.match(test, anchored):
            raise Exception(f"\"{test}\" matches: {pattern_text}")


def test_integer_pattern():
    execute_pattern_test(
        pattern=SchemaPatterns().integer,
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
        invalid_examples=[
            "0.5",
            "a",
            "1.0",
            "-9999.0"
        ])


def test_data_type_pattern():

    execute_pattern_test(
        pattern=SchemaPatterns().data_types,
        valid_examples=[
            "Numeric",
            "[Numeric]",
            "{DataGroup}",
            "[String][1..]",
        ],
        invalid_examples=[
            "Wrong"
        ])


def test_enumerator_pattern():

    execute_pattern_test(pattern=SchemaPatterns().enumerator,
                         valid_examples=[
        "ENUMERATOR",
        "ENUMERATOR_2",
        "NEW_ENUMERATOR",
        "A",
    ],
        invalid_examples=[
        "Wrong",
        "wrong",
        "_A",
        "A_",
        "000_A"
    ],
        anchored=True)


def test_value_pattern():
    execute_pattern_test(
        pattern=SchemaPatterns().values,
        valid_examples=[
            "3.14",
            "\"\"",
            "\"String\"",
            "True",
            "False",
            "ENUMERATOR",
            "ENUMERATOR_2",
            "NEW_ENUMERATOR"
        ],
        invalid_examples=[
            "Wrong",
            "true",
            "false"
        ],
        anchored=True)


def test_data_element_value_constraint_pattern():

    execute_pattern_test(
        pattern=SchemaPatterns().data_element_value_constraint,
        valid_examples=[
            "schema=RS0001"
        ],
        invalid_examples=[
            "Wrong",
            "data_element=wronG"
        ],
        anchored=True)


def test_selector_constraint_pattern():

    execute_pattern_test(
        pattern=SchemaPatterns().selector_constraint,
        valid_examples=[
            "operation_speed_control_type(CONTINUOUS, DISCRETE)"
        ],
        invalid_examples=[],
        anchored=True)
