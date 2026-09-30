import pathlib

import pytest

from lattice.file_io import dump
from lattice.schema import Schema


def _write_schema(tmp_path: pathlib.Path, groups: dict) -> pathlib.Path:
    schema_path = tmp_path / "Selector.schema.yaml"
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


# Mirrors Statistics.percent_exceedance: an Alternative(...) field selected by a sibling
# Enumeration, where only one branch ("Coincident") has a field ("coincident_values") that is
# missing a required attribute (Units) — deliberately, to prove pruning actually skips it.
_SELECTOR_GROUPS = {
    "StatType": {
        "Object Type": "Enumeration",
        "Enumerators": {
            "SINGLE_VALUE": {"Description": "d"},
            "COINCIDENT_VALUES": {"Description": "d"},
        },
    },
    "Grid": {
        "Object Type": "Data Group",
        "Data Elements": {
            "values": {"Description": "d", "Type": "Array(Numeric)", "Units": "-"},
        },
    },
    "Coincident": {
        "Object Type": "Data Group",
        "Data Elements": {
            "values": {"Description": "d", "Type": "Array(Numeric)", "Units": "-"},
            "coincident_values": {"Description": "d", "Type": "Array(Numeric)"},
        },
    },
    "Statistics": {
        "Object Type": "Data Group",
        "Data Elements": {
            "statistic_type": {"Description": "d", "Type": "Enumeration(StatType)"},
            "percent_exceedance": {
                "Description": "d",
                "Type": "Alternative(Group(Grid), Group(Coincident))",
                "Constraints": "statistic_type(SINGLE_VALUE, COINCIDENT_VALUES)",
            },
        },
    },
}


def test_without_a_pin_both_alternative_branches_are_validated(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_SELECTOR_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {"Description": "d", "Type": "Group(Statistics)"},
                },
            },
        },
    )
    with pytest.raises(Exception, match='Missing required attribute, "Units"'):
        Schema(schema_path)


def test_pinned_selector_prunes_the_other_alternative_branch(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            **_SELECTOR_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Constraints": "statistic_type=SINGLE_VALUE",
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_pinned_selector_to_the_other_value_still_validates_that_branch(tmp_path):
    # Pinning to COINCIDENT_VALUES should prune Grid instead, so the missing Units on
    # coincident_values still surfaces (it isn't just "pruning always wins").
    schema_path = _write_schema(
        tmp_path,
        {
            **_SELECTOR_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Group(Statistics)",
                        "Constraints": "statistic_type=COINCIDENT_VALUES",
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match='Missing required attribute, "Units"'):
        Schema(schema_path)


def test_nested_pin_through_an_intermediate_group(tmp_path):
    # Mirrors the real usage: dry_bulb_temperature -> annual -> Statistics.statistic_type,
    # pinned two levels up from where percent_exceedance is declared.
    schema_path = _write_schema(
        tmp_path,
        {
            **_SELECTOR_GROUPS,
            "Container": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "annual": {"Description": "d", "Type": "Group(Statistics)"},
                },
            },
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Group(Container)",
                        "Constraints": "annual.statistic_type=SINGLE_VALUE",
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_alternation_pin_covers_multiple_branches_at_once(tmp_path):
    # (annual|monthly).statistic_type=SINGLE_VALUE should pin both in one declaration.
    schema_path = _write_schema(
        tmp_path,
        {
            **_SELECTOR_GROUPS,
            "Container": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "annual": {"Description": "d", "Type": "Group(Statistics)"},
                    "monthly": {"Description": "d", "Type": "Group(Statistics)"},
                },
            },
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Group(Container)",
                        "Constraints": "(annual|monthly).statistic_type=SINGLE_VALUE",
                    },
                },
            },
        },
    )
    Schema(schema_path)


def test_data_element_value_constraint_rejects_unknown_nested_field(tmp_path):
    schema_path = _write_schema(
        tmp_path,
        {
            "Container": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "annual": {"Description": "d", "Type": "Group(Statistics)"},
                },
            },
            **_SELECTOR_GROUPS,
            "RootGroup": {
                "Object Type": "Data Group",
                "Data Elements": {
                    "thing": {
                        "Description": "d",
                        "Type": "Group(Container)",
                        "Constraints": "annual.not_a_field=SINGLE_VALUE",
                    },
                },
            },
        },
    )
    with pytest.raises(Exception, match="which was not found in Data Group"):
        Schema(schema_path)
