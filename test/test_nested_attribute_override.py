import pathlib

import pytest

from lattice.file_io import dump
from lattice.schema import Schema, _find_override_value, _path_matches


def _write_schema(tmp_path: pathlib.Path, groups: dict) -> pathlib.Path:
    schema_path = tmp_path / "Nested.schema.yaml"
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


# A "Statistics"-like generic group: a Numeric field with no Units of its own, reused by
# multiple occurrences that each need to supply Units contextually.
_STATISTICS_GROUPS = {
    "Statistics": {
        "Object Type": "Data Group",
        "Data Elements": {
            "mean": {"Description": "d", "Type": "Numeric"},
            "maximum": {"Description": "d", "Type": "Numeric"},
        },
    },
    "SummaryData": {
        "Object Type": "Data Group",
        "Data Elements": {
            "annual": {"Description": "d", "Type": "Group(Statistics)"},
        },
    },
}


def test_missing_deferred_attribute_without_override_still_raises(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_STATISTICS_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {"Description": "d", "Type": "Group(SummaryData)"},
                },
            },
        },
    )
    with pytest.raises(Exception, match='Missing required attribute, "Units"'):
        Schema(schema_path)


def test_single_level_nested_attribute_supplies_missing_units(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Statistics": _STATISTICS_GROUPS["Statistics"],
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Nested Attribute Overrides": {
                            "Units": [
                                {"path": "mean", "value": "K"},
                                {"path": "maximum", "value": "K"},
                            ],
                        },
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_deep_nested_attribute_supplies_missing_units(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_STATISTICS_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(SummaryData)",
                        "Nested Attribute Overrides": {
                            "Units": [
                                {"path": "annual.mean", "value": "K"},
                                {"path": "annual.maximum", "value": "K"},
                            ],
                        },
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_deep_nested_attribute_works_when_referencing_group_declared_later_in_file(tmp_path):
    # Validating a multi-segment path requires knowing the intermediate Data Group (e.g.
    # "annual" -> Statistics) before that Data Group's own Data Elements have necessarily been
    # resolved. Declaring RootGroup *before* SummaryData/Statistics in the source dict (as
    # ClimateInformation.schema.yaml does) reproduces that ordering; the fixed version looks the
    # group up by name instead of depending on prior resolution.
    schema_path = _write_schema(
        tmp_path,
        {
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(SummaryData)",
                        "Nested Attribute Overrides": {
                            "Units": [
                                {"path": "annual.mean", "value": "K"},
                                {"path": "annual.maximum", "value": "K"},
                            ],
                        },
                    },
                },
            },
            **_STATISTICS_GROUPS,
        },
    )
    Schema(schema_path)


def test_alternation_group_supplies_missing_units_at_a_deep_path(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_STATISTICS_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(SummaryData)",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "annual.(mean|maximum)", "value": "K"},
                        },
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_two_occurrences_of_shared_group_do_not_contaminate_each_other(tmp_path):
    # dry_bulb_temperature and relative_humidity both use Group(SummaryData) -> Group(Statistics),
    # but supply different Units. Neither should see the other's value, and the shared
    # Statistics.mean Data Element itself must not be mutated.
    schema_path = _write_schema(
        tmp_path,
        {
            **_STATISTICS_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(SummaryData)",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "annual.(mean|maximum)", "value": "K"},
                        },
                    },
                    "relative_humidity": {
                        "Description": "d",
                        "Type": "Group(SummaryData)",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "annual.(mean|maximum)", "value": "-"},
                        },
                    },
                },
            },
        },
    )
    schema = Schema(schema_path)
    mean = schema.get_data_group("Statistics").data_elements["mean"]
    assert "Units" not in mean.dictionary


def test_specific_override_takes_precedence_over_a_broader_alternation(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_STATISTICS_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(SummaryData)",
                        "Nested Attribute Overrides": {
                            "Units": [
                                {"path": "annual.(mean|maximum)", "value": "K"},
                                {"path": "annual.mean", "value": "degF"},
                            ],
                        },
                    },
                },
            },
        },
    )
    schema = Schema(schema_path)
    element = schema.root_data_group.data_elements["dry_bulb_temperature"]
    assert _find_override_value("Units", [(element, ["annual", "mean"])]) == "degF"
    assert _find_override_value("Units", [(element, ["annual", "maximum"])]) == "K"


def test_required_override_is_registered_and_resolvable(tmp_path):
    # A parent adopting a shared Data Group may want a field that's normally optional to be
    # Required in this specific context (e.g. "for most cases I don't need this, but in this
    # context I do").
    schema_path = _write_schema(
        tmp_path,
        {
            "Statistics": _STATISTICS_GROUPS["Statistics"],
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "(mean|maximum)", "value": "K"},
                            "Required": {"path": "maximum", "value": "True"},
                        },
                    },
                },
            },
        },
    )
    schema = Schema(schema_path)
    element = schema.root_data_group.data_elements["dry_bulb_temperature"]
    assert _find_override_value("Required", [(element, ["maximum"])]) == "True"
    assert _find_override_value("Required", [(element, ["mean"])]) is None


def test_constraints_override_value_may_be_a_list_of_simultaneous_constraints(tmp_path):
    # Mirrors how a Data Element's own "Constraints" key accepts a list: all listed constraints
    # apply together to the same path.
    schema_path = _write_schema(
        tmp_path,
        {
            "Statistics": _STATISTICS_GROUPS["Statistics"],
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "(mean|maximum)", "value": "K"},
                            "Constraints": {"path": "mean", "value": [">0", "<1000"]},
                        },
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_constraints_override_list_rejected_if_any_value_is_incompatible(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Statistics": _STATISTICS_GROUPS["Statistics"],
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "(mean|maximum)", "value": "K"},
                            # A string-pattern constraint can't apply to a Numeric field, even
                            # though ">0" alone would.
                            "Constraints": {"path": "mean", "value": [">0", '"[A-Z]{2}"']},
                        },
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="does not apply at occurrence"):
        Schema(schema_path)


# A group with mixed field types, to exercise Constraints-override applicability: "value" is
# Numeric (a range constraint applies), "label" is a String (it doesn't).
_MIXED_GROUP = {
    "Mixed": {
        "Object Type": "Data Group",
        "Data Elements": {
            "value": {"Description": "d", "Type": "Numeric", "Units": "-"},
            "label": {"Description": "d", "Type": "String"},
        },
    },
}


def test_literal_constraints_override_applies_to_compatible_target(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_MIXED_GROUP,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Group(Mixed)",
                        "Nested Attribute Overrides": {"Constraints": {"path": "value", "value": ">0"}},
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_literal_constraints_override_rejected_for_incompatible_target(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_MIXED_GROUP,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Group(Mixed)",
                        # "label" is a String, not a Numeric/Integer — RangeConstraint ">0"
                        # can never apply to it.
                        "Nested Attribute Overrides": {"Constraints": {"path": "label", "value": ">0"}},
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="does not apply at occurrence"):
        Schema(schema_path)


def test_unsupported_attribute_name_is_rejected(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Statistics": _STATISTICS_GROUPS["Statistics"],
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Nested Attribute Overrides": {"Notes": {"path": "mean", "value": "not supported"}},
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="Unsupported attribute"):
        Schema(schema_path)


def test_missing_path_or_value_key_is_rejected(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Statistics": _STATISTICS_GROUPS["Statistics"],
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Nested Attribute Overrides": {"Units": {"path": "mean"}},
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="must be a mapping with 'path' and 'value' keys"):
        Schema(schema_path)


def test_literal_path_segment_not_found_is_rejected(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Statistics": _STATISTICS_GROUPS["Statistics"],
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Nested Attribute Overrides": {"Units": {"path": "not_a_field", "value": "K"}},
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="which was not found in Data Group"):
        Schema(schema_path)


def test_alternation_segment_covers_multiple_named_fields(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_STATISTICS_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(SummaryData)",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "annual.(mean|maximum)", "value": "K"},
                        },
                    },
                },
            },
        },
    )
    schema = Schema(schema_path)
    element = schema.root_data_group.data_elements["dry_bulb_temperature"]
    assert _find_override_value("Units", [(element, ["annual", "mean"])]) == "K"
    assert _find_override_value("Units", [(element, ["annual", "maximum"])]) == "K"


def test_alternation_segment_unknown_member_is_rejected(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Statistics": _STATISTICS_GROUPS["Statistics"],
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "dry_bulb_temperature": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "(mean|not_a_field)", "value": "K"},
                        },
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="which was not found in Data Group"):
        Schema(schema_path)


def test_alternation_segment_mismatch_is_an_error(tmp_path):
    # An alternation names its targets explicitly, so a mismatch is an authoring error.
    schema_path = _write_schema(
        tmp_path,
        {
            **_MIXED_GROUP,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Group(Mixed)",
                        "Nested Attribute Overrides": {
                            "Constraints": {"path": "(value|label)", "value": ">0"},
                        },
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="does not apply at occurrence"):
        Schema(schema_path)


# An Alternative(...)-typed field, mirroring Statistics.percent_exceedance: one branch has a
# single "values" array, the other has both "values" and "coincident_values" (a second variable
# reported at the same grid points as "values").
_ALTERNATIVE_GROUPS = {
    "Grid": {
        "Object Type": "Data Group",
        "Data Elements": {
            "values": {"Description": "d", "Type": "Array(Numeric)"},
        },
    },
    "Coincident": {
        "Object Type": "Data Group",
        "Data Elements": {
            "values": {"Description": "d", "Type": "Array(Numeric)"},
            "coincident_values": {"Description": "d", "Type": "Array(Numeric)"},
        },
    },
}


def test_missing_units_is_caught_through_an_alternative_type(tmp_path):
    # Regression test: the occurrence walker used to stop at Alternative(...)-typed fields
    # entirely, silently skipping required-attribute validation for everything beneath them.
    schema_path = _write_schema(
        tmp_path,
        {
            **_ALTERNATIVE_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {"Description": "d", "Type": "Alternative(Group(Grid), Group(Coincident))"},
                },
            },
        },
    )
    with pytest.raises(Exception, match='Missing required attribute, "Units"'):
        Schema(schema_path)


def test_alternation_reaches_every_field_across_alternative_branches(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_ALTERNATIVE_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Alternative(Group(Grid), Group(Coincident))",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "(values|coincident_values)", "value": "K"},
                        },
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_literal_path_can_target_a_field_only_present_in_one_alternative_branch(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_ALTERNATIVE_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Alternative(Group(Grid), Group(Coincident))",
                        "Nested Attribute Overrides": {
                            "Units": [
                                {"path": "values", "value": "K"},
                                {"path": "coincident_values", "value": "m/s"},
                            ],
                        },
                    },
                },
            },
        },
    )
    schema = Schema(schema_path)
    element = schema.root_data_group.data_elements["thing"]
    assert _find_override_value("Units", [(element, ["values"])]) == "K"
    assert _find_override_value("Units", [(element, ["coincident_values"])]) == "m/s"


def test_literal_path_through_alternative_rejects_unknown_field(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_ALTERNATIVE_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Alternative(Group(Grid), Group(Coincident))",
                        "Nested Attribute Overrides": {
                            "Units": {"path": "not_a_field", "value": "K"},
                        },
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="which was not found in Data Group"):
        Schema(schema_path)


@pytest.mark.parametrize(
    ("pattern", "actual", "expected"),
    [
        (["annual", "mean"], ["annual", "mean"], True),
        (["annual", "mean"], ["annual", "maximum"], False),
        (["annual", "mean"], ["annual"], False),
        (["annual", "mean"], ["annual", "mean", "extra"], False),
        (["annual", ("mean", "maximum")], ["annual", "mean"], True),
        (["annual", ("mean", "maximum")], ["annual", "maximum"], True),
        (["annual", ("mean", "maximum")], ["annual", "minimum"], False),
        ((("annual", "monthly"), ("mean", "maximum")), ["monthly", "maximum"], True),
        ((("annual", "monthly"), ("mean", "maximum")), ["weekly", "maximum"], False),
    ],
)
def test_path_matches(pattern, actual, expected):
    assert _path_matches(list(pattern), actual) == expected
