"""Keep compound denominator products grouped in human-readable units."""

import pytest

from lattice.docs.schema_table import data_elements_dict_from_data_groups


@pytest.mark.parametrize(
    ("units", "expected"),
    [
        ("W/m2-K", "W/(m^2^·K)"),
        ("kg-m/s2-K", "kg·m/(s^2^·K)"),
        ("W/m2-K-s", "W/(m^2^·K·s)"),
        ("m3/s", "m^3^/s"),
        ("kg-m", "kg·m"),
        ("-", r"\-"),
        ("W/(m2-K)", "W/(m^2^·K)"),
    ],
)
def test_units_group_compound_denominator(units, expected):
    source = {"Example": {"Data Elements": {"quantity": {"Units": units}}}}
    rendered = data_elements_dict_from_data_groups(source)
    assert rendered["Example"][0]["Units"] == expected
    assert source["Example"]["Data Elements"]["quantity"]["Units"] == units
