import yaml

from lattice.cpp.header_entries import DataElement, Enumeration, HeaderEntry, Struct
from lattice.cpp.header_translator import ReferencedDataType

alternative_schema = yaml.safe_load("""
SpeedControlType:
    Object Type: "Enumeration"
    Enumerators:
        DISCRETE:
            Description: "Loading is controlled by cycling between one or more discrete stages"
            Display Text: "Discrete"
        CONTINUOUS:
            Description: "Loading is controlled by continuously varying the speed"
            Display Text: "Continuous"
Performance:
    Object Type: "Data Group"
    Data Elements:
        operation_speed_control_type:
            Description: "Type of performance map"
            Type: "<SpeedControlType>"
            Required: True
        performance_map:
            Description: "Data group describing fan assembly performance when operating"
            Type: "({PerformanceMapContinuous}, {PerformanceMapDiscrete})"
            Constraints: "operation_speed_control_type(CONTINUOUS, DISCRETE)"
            Required: True
    """)

array_schema = yaml.safe_load("""
LookupVariables:
    Object Type: "Data Group"
    Data Group Template: LookupVariablesTemplate
    Data Elements:
        efficiency:
            Description: "Efficiency of drive"
            Type: "[Numeric]"
            Constraints:
            - ">=0.0"
            - "<=1.0"
            - "[1..]"
            Units: "-"
            Notes: "Defined as the ratio of output shaft power to input shaft power"
            Required: True
        operation_state:
            Description: "The operation state at the operating conditions"
            Type: "[<OperationState>]"
            Units: "-"
            Required: True
    """)


def test_namespace():
    code = HeaderEntry("test", None)
    assert "namespace test" in str(code)


def test_enumeration():
    assert alternative_schema is not None and isinstance(alternative_schema, dict)
    enum = "SpeedControlType"
    e = Enumeration(enum, None, alternative_schema[enum]["Enumerators"])  # this could be in a separate test
    assert "UNKNOWN" in str(e)
    assert "DISCRETE" in str(e)


def test_array_data_element():
    assert array_schema is not None and isinstance(array_schema, dict)
    group = "LookupVariables"
    data_element = "operation_state"
    s = Struct(group, None)
    _ = DataElement(
        data_element,
        s,
        array_schema[group]["Data Elements"],
        {"Numeric": "double"},
        [ReferencedDataType("OperationState", "", "")],
    )
    assert "std::vector<OperationState>" in str(s)


def test_enum_data_element():
    assert alternative_schema is not None and isinstance(alternative_schema, dict)

    enum = "SpeedControlType"
    group = "Performance"
    data_element = "operation_speed_control_type"
    s = Struct(group, None)
    _ = DataElement(
        data_element,
        s,
        alternative_schema[group]["Data Elements"],
        {"Numeric": "double"},
        [ReferencedDataType(enum, "", "")],
    )
    assert "SpeedControlType operation_speed_control_type;" in str(s)


def test_base_class_declaration():
    schema = yaml.safe_load("""
    PerformanceMapContinuous:
        Object Type: "Data Group"
        Data Group Template: PerformanceMapTemplate
        Data Elements:
            grid_variables:
                Description: "Data group describing grid variables for continuous fan performance"
                Type: "[Numeric]"
                Required: True
            lookup_variables:
                Description: "Data group describing lookup variables for continuous fan performance"
                Type: "[Numeric]"
                Required: True
        """)
    assert schema is not None and isinstance(schema, dict)
    group = "PerformanceMapContinuous"
    s = Struct(group, None, schema[group].get("Data Group Template", ""))
    assert ": PerformanceMapTemplate" in str(s)


def test_base_class_pointer():
    assert alternative_schema is not None and isinstance(alternative_schema, dict)
    top = HeaderEntry("test", None)

    enum = "SpeedControlType"
    group = "Performance"
    data_element = "performance_map"
    s = Struct(group, top)
    _ = DataElement(
        data_element,
        s,
        alternative_schema[group]["Data Elements"],
        {"Numeric": "double"},
        [
            ReferencedDataType(enum, "", ""),
            ReferencedDataType("PerformanceMapContinuous", "", "PerformanceMapTemplate"),
            ReferencedDataType("PerformanceMapDiscrete", "", "PerformanceMapTemplate"),
            ReferencedDataType("PerformanceMapTemplate", "", None),
        ],
    )
    assert "std::unique_ptr<PerformanceMapTemplate>" in str(s)
