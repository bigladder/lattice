from __future__ import (
    annotations,
)  # Needed for type hinting classes that are not yet fully defined

import pathlib
import re
import warnings
from typing import Any, Dict, List, Type, Union

from .file_io import get_file_basename, load

core_schema_path = pathlib.Path(pathlib.Path(__file__).parent, "core.schema.yaml")


class RegularExpressionPattern:
    def __init__(self, pattern_string: str) -> None:
        self.pattern = re.compile(pattern_string)
        self.anchored_pattern = re.compile(self.anchor(pattern_string))

    def __str__(self):
        return self.pattern.pattern

    def match(
        self, test_string: str, anchored: bool = False
    ) -> Union[re.Match[str], None]:
        return (
            self.pattern.match(test_string)
            if not anchored
            else self.anchored_pattern.match(test_string)
        )

    def anchored(self):
        return self.anchored_pattern.pattern

    @staticmethod
    def anchor(pattern_text: str) -> str:
        return f"^{pattern_text}$"


# Attributes

# Data Types
_type_base_names = RegularExpressionPattern("[A-Z]([A-Z]|[a-z]|[0-9])*")
_data_element_names = RegularExpressionPattern("([a-z][a-z,0-9]*)(_([a-z,0-9])+)*")


class DataType:
    pattern: RegularExpressionPattern
    value_pattern: RegularExpressionPattern

    def __init__(self, text: str, parent_data_element: DataElement):
        self.text = text
        self.parent_data_element = parent_data_element

    def get_path(self) -> str:
        return (
            f"{self.parent_data_element.parent_data_group.parent_schema.name}."
            f"{self.parent_data_element.parent_data_group.name}."
            f"{self.parent_data_element.name}."
            f"Data Type"
        )

    def resolve(self):
        pass


class IntegerType(DataType):
    pattern = RegularExpressionPattern("(Integer)")
    value_pattern = RegularExpressionPattern("([-+]?[0-9]+)")


class NumericType(DataType):
    pattern = RegularExpressionPattern("(Numeric)")
    value_pattern = RegularExpressionPattern(
        "([-+]?[0-9]*\\.?[0-9]+([eE][-+]?[0-9]+)?)"
    )


class BooleanType(DataType):
    pattern = RegularExpressionPattern("(Boolean)")
    value_pattern = RegularExpressionPattern("True|False")


class StringType(DataType):
    pattern = RegularExpressionPattern("(String)")
    value_pattern = RegularExpressionPattern('".*"')


class PatternType(DataType):
    pattern = RegularExpressionPattern("(Pattern)")
    value_pattern = RegularExpressionPattern('".*"')


class DataGroupType(DataType):
    pattern = RegularExpressionPattern(rf"\{{({_type_base_names})\}}")

    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)
        match = self.pattern.match(text)
        assert match is not None
        self.data_group_name = match.group(1)
        self.data_group = None  # only valid once resolve() is called

    def resolve(self):
        self.data_group = (
            self.parent_data_element.parent_data_group.parent_schema.get_data_group(
                self.data_group_name
            )
        )


class EnumerationType(DataType):
    pattern = RegularExpressionPattern(rf"<{_type_base_names}>")
    value_pattern = RegularExpressionPattern("([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*")


class AlternativeType(DataType):
    pattern = RegularExpressionPattern(r"\(([^\s,]+)((, ?([^\s,]+))+)\)")


class ReferenceType(DataType):
    pattern = RegularExpressionPattern(rf":{_type_base_names}:")


class ArrayType(DataType):
    pattern = RegularExpressionPattern(
        rf"\[({_type_base_names}|{DataGroupType.pattern}|{EnumerationType.pattern})\]"
    )


_value_pattern = RegularExpressionPattern(
    f"(({NumericType.value_pattern})|"
    f"({StringType.value_pattern})|"
    f"({EnumerationType.value_pattern})|"
    f"({BooleanType.value_pattern}))"
)


# Constraints
class Constraint:
    pattern: RegularExpressionPattern

    def __init__(self, text: str, parent_data_element: DataElement):
        self.text = text
        self.parent_data_element = parent_data_element

    def resolve(self):
        pass


class RangeConstraint(Constraint):
    pattern = RegularExpressionPattern(f"(>|>=|<=|<)({NumericType.value_pattern})")


class MultipleConstraint(Constraint):
    pattern = RegularExpressionPattern(f"%({NumericType.value_pattern})")


class SetConstraint(Constraint):
    pattern = RegularExpressionPattern(
        rf"\[{NumericType.value_pattern}(, ?{NumericType.value_pattern})*\]"
    )


class SelectorConstraint(Constraint):
    pattern = RegularExpressionPattern(
        rf"{_data_element_names}\({EnumerationType.value_pattern}(, ?{EnumerationType.value_pattern})*\)"
    )


class StringPatternConstraint(Constraint):
    pattern = RegularExpressionPattern('".*"')

    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)
        try:
            re.compile(text)
        except re.error:
            raise Exception(
                f"Invalid regular expression: {text}"
            )  # pylint:disable=W0707


class DataElementValueConstraint(Constraint):
    pattern = RegularExpressionPattern(f"({_data_element_names})=({_value_pattern})")

    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)
        self.pattern = (
            parent_data_element.parent_data_group.parent_schema.schema_patterns.data_element_value_constraint
        )
        match = self.pattern.match(self.text)
        assert match is not None
        # parent data element must be a data group
        if not isinstance(self.parent_data_element.data_type, DataGroupType):
            raise Exception(
                f"Data Element Value Constraint must be a Data Group Type, not {type(self.parent_data_element)}"
            )

        self.data_element_name = match.group(1)  # TODO: Named groups?
        self.data_element_value = match.group(5)
        self.data_element: DataElement

    def resolve(self):
        assert isinstance(self.parent_data_element.data_type, DataGroupType)
        if (
            self.data_element_name
            not in self.parent_data_element.data_type.data_group.data_elements
        ):
            raise Exception(
                f"Data Element Value Constraint '{self.data_element_name}' not found in Data Group '{self.parent_data_element.data_type.data_group_name}'"
            )

        self.data_element = self.parent_data_element.data_type.data_group.data_elements[
            self.data_element_name
        ]
        match = self.data_element.data_type.value_pattern.match(self.data_element_value)
        if match is None:
            raise Exception(
                f"Data Element Value Constraint '{self.data_element_value}' does not match the value pattern of '{self.data_element.name}'"
            )


class ArrayLengthLimitsConstraint(Constraint):
    pattern = RegularExpressionPattern(r"\[(\d*)\.\.(\d*)\]")


_constraint_list: List[Type[Constraint]] = [
    RangeConstraint,
    MultipleConstraint,
    SetConstraint,
    SelectorConstraint,
    StringPatternConstraint,
    DataElementValueConstraint,
    ArrayLengthLimitsConstraint,
]


def _constraint_factory(text: str, parent_data_element: DataElement) -> Constraint:
    number_of_matches = 0
    for constraint in _constraint_list:
        if constraint.pattern.match(text):
            match_type = constraint
            number_of_matches += 1

    if number_of_matches == 1:
        return match_type(text, parent_data_element)
    if number_of_matches == 0:
        raise Exception(
            f"No matching constraint for {text} in element {parent_data_element.name}."
        )
    raise Exception(f"Multiple matches found for constraint, {text}")


# Required


class DataElement:
    pattern = _data_element_names

    def __init__(
        self, name: str, data_element_dictionary: dict, parent_data_group: DataGroup
    ):
        self.name = name
        self.dictionary = data_element_dictionary
        self.parent_data_group = parent_data_group
        self.constraints: List[Constraint] = []
        self.is_id = False
        for attribute in self.dictionary:
            if attribute == "Description":
                self.description = self.dictionary[attribute]
            elif attribute == "Units":
                self.units = self.dictionary[attribute]
            elif attribute == "Data Type":
                self.data_type = self.get_data_type(
                    parent_data_group, self.dictionary[attribute]
                )
            elif attribute == "Constraints":
                self.set_constraints(self.dictionary[attribute])
            elif attribute == "Required":
                self.required = self.dictionary[attribute]
            elif attribute == "Notes":
                self.notes = self.dictionary[attribute]
            elif attribute == "ID":
                self.is_id = self.dictionary[attribute]
                if self.is_id:
                    if self.parent_data_group.id_data_element is None:
                        self.parent_data_group.id_data_element = self
                    else:
                        raise RuntimeError(
                            f"Multiple ID data elements found for Data Group '{self.parent_data_group.name}':"
                            f" '{self.parent_data_group.id_data_element.name}' and '{self.name}'"
                        )

            else:
                warnings.warn(
                    f'Unrecognized attribute, "{attribute}".'
                    f"Schema={self.parent_data_group.parent_schema.file_path},"
                    f"Data Group={self.parent_data_group.name},"
                    f"Data Element={self.name}"
                )

    def get_data_type(
        self, parent_data_group: DataGroup, attribute_str: str
    ) -> DataType:
        """
        Returns the data type from the attribute string.
        """
        try:
            return self.parent_data_group.parent_schema.data_type_factory(
                attribute_str, self
            )
        except RuntimeError:
            for (
                reference_schema
            ) in self.parent_data_group.parent_schema.reference_schemas.values():
                try:
                    return reference_schema.data_type_factory(attribute_str, self)
                except RuntimeError:
                    continue

    def set_constraints(self, constraints_input: Union[str, List[str]]) -> None:
        if not isinstance(constraints_input, list):
            constraints_input = [constraints_input]

        for constraint in constraints_input:
            self.constraints.append(_constraint_factory(constraint, self))

    def resolve(self):
        self.data_type.resolve()
        for constraint in self.constraints:
            constraint.resolve()


class FundamentalDataType:
    def __init__(self, name: str, data_type_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = data_type_dictionary
        self.parent_schema = parent_schema


class CommonStringType:
    def __init__(self, name: str, string_type_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = string_type_dictionary
        self.parent_schema = parent_schema
        self.value_pattern = self.dictionary["Regular Expression Pattern"]

        # Make new DataType class
        def init_method(self, text, parent_data_element):
            StringType.__init__(self, text, parent_data_element)

        self.data_type_class = type(
            self.name,
            (StringType,),
            {
                "__init__": init_method,
                "pattern": RegularExpressionPattern(self.name),
                "value_pattern": RegularExpressionPattern(self.value_pattern),
            },
        )

        parent_schema.add_data_type(self.data_type_class)


class DataGroup:
    def __init__(self, name: str, data_group_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = data_group_dictionary
        self.parent_schema = parent_schema
        self.data_elements: dict[str, DataElement] = {}
        self.id_data_element: Union[DataElement, None] = (
            None  # data element containing unique id for this data group
        )
        for data_element in self.dictionary["Data Elements"]:
            self.data_elements[data_element] = DataElement(
                data_element, self.dictionary["Data Elements"][data_element], self
            )

    def resolve(self):
        for data_element in self.data_elements.values():
            data_element.resolve()


class Enumerator:
    pattern = EnumerationType.value_pattern

    def __init__(
        self, name: str, enumerator_dictionary: dict, parent_enumeration: Enumeration
    ):
        self.name = name
        self.dictionary = enumerator_dictionary
        self.parent_enumeration = parent_enumeration


class Enumeration:
    def __init__(self, name: str, enumeration_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = enumeration_dictionary
        self.parent_schema = parent_schema
        self.enumerators = {}
        for enumerator in self.dictionary["Enumerators"]:
            self.enumerators[enumerator] = Enumerator(
                enumerator, self.dictionary["Enumerators"][enumerator], self
            )


class DataGroupTemplate:
    def __init__(
        self, name: str, data_group_template_dictionary: dict, parent_schema: Schema
    ):
        self.name = name
        self.dictionary = data_group_template_dictionary
        self.parent_schema = parent_schema


class SchemaPatterns:
    # TODO: Remove in favor of class members of respective classes?
    numeric = NumericType.value_pattern
    integer = IntegerType.value_pattern
    string = StringType.value_pattern
    enumerator = Enumerator.pattern
    boolean = BooleanType.value_pattern

    data_group_names = _type_base_names
    enumeration_names = _type_base_names
    data_element_names = DataElement.pattern
    type_base_names = _type_base_names

    def __init__(self, schema=None):
        # Generate Regular Expressions
        core_schema = load(core_schema_path)

        # Fundamental Data Types (from core schema)
        core_types = get_types(core_schema)
        self.combined_types = set(core_types.keys())

        regex_base_types = core_types["Data Type"]

        base_types_string = "|".join(regex_base_types)
        base_types = RegularExpressionPattern(f"({base_types_string})")

        string_types = core_types["String Type"]
        if schema:
            schema_types = get_types(schema)
            self.combined_types |= set(schema_types.keys())
            if "String Type" in schema_types:
                string_types += ["String Type"]

        re_string_types_string = "|".join(string_types)
        re_string_types = RegularExpressionPattern(f"({re_string_types_string})")

        self.data_group_types = DataGroupType.pattern
        self.enumeration_types = EnumerationType.pattern
        references = ReferenceType.pattern
        single_type = rf"({base_types}|{re_string_types}|{self.data_group_types}|{self.enumeration_types}|{references})"
        alternatives = rf"\(({single_type})(,\s*{single_type})+\)"
        arrays = ArrayType.pattern
        self.data_types = RegularExpressionPattern(
            f"({single_type})|({alternatives})|({arrays})"
        )

        # Values
        self.values = RegularExpressionPattern(
            f"(({self.numeric})|({self.string})|({self.enumerator})|({self.boolean}))"
        )

        # Constraints
        self.range_constraint = RangeConstraint.pattern
        self.multiple_constraint = MultipleConstraint.pattern
        self.data_element_value_constraint = DataElementValueConstraint.pattern
        sets = SetConstraint.pattern
        reference_scope = f":{_type_base_names}:"
        self.selector_constraint = SelectorConstraint.pattern
        array_limits = ArrayLengthLimitsConstraint.pattern
        string_patterns = StringPatternConstraint.pattern

        self.constraints = RegularExpressionPattern(
            f"({self.range_constraint})|"  # pylint:disable=C0301
            f"({self.multiple_constraint})|"
            f"({sets})|"
            f"({self.data_element_value_constraint})|"
            f"({reference_scope})|"
            f"({self.selector_constraint})|"
            f"({array_limits})|"
            f"({string_patterns})"
        )

        # Conditional Requirements
        self.conditional_requirements = RegularExpressionPattern(
            f"if (!?{self.data_element_names})(!?=({self.values}))?"
        )


class Schema:
    def __init__(
        self, file_path: pathlib.Path, parent_schema: Schema | None = None
    ):  # noqa: PLR0912
        self.file_path = file_path.absolute()
        self.source_dictionary = load(self.file_path)
        self.name = get_file_basename(self.file_path, depth=2)
        if "Schema" not in self.source_dictionary:
            raise Exception(f'"Schema" node not found in {self.file_path}')

        self.parent_schema = parent_schema
        self.data_types = {}
        self.string_types = {}
        self.enumerations = {}
        self.data_groups = {}
        self.data_group_templates = {}

        self._data_type_list: List[Type[DataType]] = [
            IntegerType,
            NumericType,
            BooleanType,
            StringType,
            PatternType,
            ArrayType,
            DataGroupType,
            EnumerationType,
            AlternativeType,
            ReferenceType,
        ]

        self.schema_patterns = SchemaPatterns(self.source_dictionary)

        if "Schema" in self.source_dictionary:
            self.title = self.source_dictionary["Schema"]["Title"]
            self.description = self.source_dictionary["Schema"]["Description"]
            self.version = self.source_dictionary["Schema"]["Version"]
            self.root_data_group_name = (
                self.source_dictionary["Schema"]["Root Data Group"]
                if "Root Data Group" in self.source_dictionary["Schema"]
                else None
            )
            self.set_reference_schemas()

        for object_name in self.source_dictionary:
            object_type = self.source_dictionary[object_name]["Object Type"]
            if object_type == "Data Group":
                self.data_groups[object_name] = DataGroup(
                    object_name, self.source_dictionary[object_name], self
                )
            elif object_type == "Enumeration":
                self.enumerations[object_name] = Enumeration(
                    object_name, self.source_dictionary[object_name], self
                )
            elif object_type == "Data Type":
                self.data_types[object_name] = FundamentalDataType(
                    object_name, self.source_dictionary[object_name], self
                )
            elif object_type == "String Type":
                self.string_types[object_name] = CommonStringType(
                    object_name, self.source_dictionary[object_name], self
                )
            elif object_type == "Data Group Template":
                self.data_group_templates[object_name] = DataGroupTemplate(
                    object_name, self.source_dictionary[object_name], self
                )
        #    else:
        #        raise Exception(f"Unrecognized Object Type, \"{object_type}\" in {self.file_path}")

        # Get top level info
        self.root_data_group = None
        self.metadata = None
        self.schema_author = None
        self.schema_name = self.name

        if self.root_data_group_name is not None:
            self.schema_name = self.root_data_group_name
            self.root_data_group = self.get_data_group(self.root_data_group_name)
            self.metadata = (
                self.root_data_group.data_elements["metadata"]
                if "metadata" in self.root_data_group.data_elements
                else None
            )
            if self.metadata is not None:
                for constraint in self.metadata.constraints:
                    if isinstance(constraint, DataElementValueConstraint):
                        if constraint.data_element_name == "schema_author":
                            self.schema_author = constraint.data_element_value
                        elif constraint.data_element_name == "schema_name":
                            self.schema_name = constraint.data_element_value.strip('"')

        for data_group in self.data_groups.values():
            data_group.resolve()

    def set_reference_schemas(self):
        self.reference_schemas = {}
        if self.file_path != core_schema_path:
            self.set_reference_schema("core", core_schema_path)
        if "References" in self.source_dictionary["Schema"]:
            parent_directory = self.file_path.parent
            for reference in self.source_dictionary["Schema"]["References"]:
                if reference == "core":
                    raise Exception(
                        f"Illegal reference schema name, {reference}. This name is reserved."
                    )
                self.set_reference_schema(
                    reference,
                    pathlib.Path(parent_directory, f"{reference}.schema.yaml"),
                )

    def set_reference_schema(self, schema_name, schema_path):
        existing_schema = self.get_reference_schema(schema_name)

        if existing_schema is not None:
            self.reference_schemas[schema_name] = existing_schema
        else:
            self.reference_schemas[schema_name] = Schema(schema_path, self)

    def get_reference_schema(self, schema_name: str) -> Schema | None:
        # TODO: verify schema has the same path too?
        # Search this schema first
        if schema_name in self.reference_schemas:
            return self.reference_schemas[schema_name]

        # Search parent schema
        if self.parent_schema is not None:
            return self.parent_schema.get_reference_schema(schema_name)

        return None

    def get_data_group(self, data_group_name: str) -> DataGroup:
        matching_schemas = []
        # 1. Search this schema first
        if data_group_name in self.data_groups:
            matching_schemas.append(self)
        for reference_schema in self.reference_schemas.values():
            if data_group_name in reference_schema.data_groups:
                matching_schemas.append(reference_schema)

        if len(matching_schemas) == 0:
            raise Exception(
                f'Data Group "{data_group_name}" not found in "{self.file_path}" or its referenced schemas'
            )

        return matching_schemas[0].data_groups[data_group_name]

    def data_type_factory(
        self, text: str, parent_data_element: DataElement
    ) -> DataType:
        number_of_matches = 0
        for data_type in self._data_type_list:
            if data_type.pattern.match(text):
                match_type = data_type
                number_of_matches += 1

        if number_of_matches == 1:
            return match_type(text, parent_data_element)
        if number_of_matches == 0:
            raise RuntimeError(f"No matching data type for {text}.")
        else:
            raise RuntimeError(f"Multiple matches found for data type, {text}")

    def add_data_type(self, data_type: Type[DataType]) -> None:
        if data_type not in self._data_type_list:
            self._data_type_list.append(data_type)

        if self.parent_schema is not None:
            self.parent_schema.add_data_type(data_type)


def get_types(schema):
    """For each Object Type in a schema, map a list of Objects matching that type."""
    types: Dict[str, Any] = {}
    for object_name in schema:
        if schema[object_name]["Object Type"] not in types:
            types[schema[object_name]["Object Type"]] = []
        types[schema[object_name]["Object Type"]].append(object_name)
    return types
