from __future__ import (
    annotations,
)  # Needed for type hinting classes that are not yet fully defined

import pathlib
from typing import Any, Dict, List, Type, Union

import regex

from .file_io import get_file_basename, load

core_schema_path = pathlib.Path(pathlib.Path(__file__).parent, "core.schema.yaml")


class RegularExpressionPattern:
    def __init__(self, pattern_string: str) -> None:
        self.pattern = regex.compile(pattern_string)
        self.anchored_pattern = regex.compile(self.anchor(pattern_string))

    def __str__(self):
        return self.pattern.pattern

    def match(self, test_string: str, anchored: bool = False) -> Union[regex.Match, None]:
        return self.pattern.match(test_string) if not anchored else self.anchored_pattern.match(test_string)

    def anchored(self):
        return self.anchored_pattern.pattern

    def cleaned(self) -> str:
        return regex.sub(r"\?P<\w+>", "?:", self.pattern.pattern)

    @staticmethod
    def anchor(pattern_text: str) -> str:
        return f"^{pattern_text}$"


# Attributes

# Data Types
_type_base_names = RegularExpressionPattern("[A-Z]([A-Z]|[a-z]|[0-9])*")
_data_element_names = RegularExpressionPattern("([a-z][a-z,0-9]*)(_([a-z,0-9])+)*")


# Module functions


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
            f"Type"
        )

    def resolve(self):
        pass


class IntegerType(DataType):
    pattern = RegularExpressionPattern("(Integer)")
    value_pattern = RegularExpressionPattern("([-+]?[0-9]+)")


class NumericType(DataType):
    pattern = RegularExpressionPattern("(Numeric)")
    value_pattern = RegularExpressionPattern("(?P<NumericTypeValue>[-+]?[0-9]*\\.?[0-9]+([eE][-+]?[0-9]+)?)")


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
    pattern = RegularExpressionPattern(
        rf"{{(?P<DataGroupName>{_type_base_names})}}|Group\((?P<DataGroupName>{_type_base_names})\)"
    )  # noqa: E501

    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)
        match = self.pattern.match(text)
        assert match is not None
        self.data_group_name = match.group("DataGroupName")
        self.data_group = None  # only valid once resolve() is called

    def resolve(self):
        self.data_group = self.parent_data_element.parent_data_group.parent_schema.get_data_group(self.data_group_name)


class EnumerationType(DataType):
    pattern = RegularExpressionPattern(
        rf"<(?P<EnumerationTypeName>{_type_base_names})>|"
        rf"Enumeration\((?P<EnumerationTypeName>{_type_base_names})\)"
    )
    value_pattern = RegularExpressionPattern("([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*")


class AlternativeType(DataType):
    pattern = RegularExpressionPattern(
        r"\((?P<AlternativeTypeName>[^\s,]+)((, ?(?P<AlternativeTypeName>[^\s,]+))+)\)|"
        r"Alternative\((?P<AlternativeTypeName>[^\s,]+)((, ?(?P<AlternativeTypeName>[^\s,]+))+)\)"
    )  # noqa: E501


class ReferenceType(DataType):
    pattern = RegularExpressionPattern(
        rf":(?P<ReferenceTypeName>{_type_base_names}):|"
        rf"Reference\(Group\((?P<ReferenceTypeName>{_type_base_names})\)\)"
    )


class ArrayType(DataType):
    pattern = RegularExpressionPattern(
        rf"\[(?P<ArrayTypeName>{_type_base_names}|{DataGroupType.pattern}|{EnumerationType.pattern})\]|"  # noqa: E501
        rf"Array\((?P<ArrayTypeName>{_type_base_names}|{DataGroupType.pattern}|{EnumerationType.pattern})\)"
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
    pattern = RegularExpressionPattern(rf"\[{NumericType.value_pattern}(, ?{NumericType.value_pattern})*\]")


class SelectorConstraint(Constraint):
    pattern = RegularExpressionPattern(
        rf"{_data_element_names}\((?P<SelectorValue>{EnumerationType.value_pattern})(, ?(?P<SelectorValue>{EnumerationType.value_pattern}))*\)"  # noqa: E501
    )


class StringPatternConstraint(Constraint):
    pattern = RegularExpressionPattern('".*"')

    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)
        try:
            regex.compile(text)
        except regex.error:
            raise Exception(f"Invalid regular expression: {text}")  # pylint:disable=W0707


class DataElementValueConstraint(Constraint):
    pattern = RegularExpressionPattern(
        f"(?P<DataElementName>{_data_element_names})=(?P<ConstrainedValue>{_value_pattern})"
    )  # noqa: E501

    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)
        self.pattern = parent_data_element.parent_data_group.parent_schema.schema_patterns.data_element_value_constraint
        match = self.pattern.match(self.text)
        assert match is not None
        # parent data element must be a data group
        if not isinstance(self.parent_data_element.data_type, DataGroupType):
            raise Exception(
                f"Data Element Value Constraint must be a Data Group Type, not {type(self.parent_data_element)}"
            )

        self.data_element_name = match.group("DataElementName")
        self.data_element_value = match.group("ConstrainedValue")
        self.data_element: DataElement

    def resolve(self):
        assert isinstance(self.parent_data_element.data_type, DataGroupType)
        assert self.parent_data_element.data_type.data_group is not None
        if self.data_element_name not in self.parent_data_element.data_type.data_group.data_elements:
            raise Exception(
                f"Data Element Value Constraint '{self.data_element_name}' "
                "not found in Data Group '{self.parent_data_element.data_type.data_group_name}'"
            )

        self.data_element = self.parent_data_element.data_type.data_group.data_elements[self.data_element_name]
        match = self.data_element.data_type.value_pattern.match(self.data_element_value)
        if match is None:
            raise Exception(
                f"Data Element Value Constraint '{self.data_element_value}' "
                "does not match the value pattern of '{self.data_element.name}'"
            )


class DataElementValueSubConstraint(Constraint):
    pattern = RegularExpressionPattern(rf"({_data_element_names})\.Constraints=\"(({RangeConstraint.pattern},?\s?)*)\"")

    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)
        self.pattern = (
            parent_data_element.parent_data_group.parent_schema.schema_patterns.data_element_value_subconstraint
        )
        match = self.pattern.match(self.text)
        assert match is not None
        # parent data element must be a data group
        if not isinstance(self.parent_data_element.data_type, DataGroupType):
            raise Exception(
                f"Data Element Value Constraint must be a Data Group Type, not {type(self.parent_data_element)}"
            )

        self.data_element_name = match.group(1)  # TODO: Named groups?
        self.data_element_constraint = match.group(5)
        self.data_element: DataElement

    def resolve(self):
        assert isinstance(self.parent_data_element.data_type, DataGroupType)
        assert self.parent_data_element.data_type.data_group is not None
        if self.data_element_name not in self.parent_data_element.data_type.data_group.data_elements:
            raise Exception(
                f"Data Element Value Constraint '{self.data_element_name}' not found in Data Group '"
                f"{self.parent_data_element.data_type.data_group_name}'"
            )

        self.data_element = self.parent_data_element.data_type.data_group.data_elements[self.data_element_name]
        # TODO: Process the constraints for the type's element:
        self.data_element.set_constraints(self.data_element_constraint)


class ArrayLengthLimitsConstraint(Constraint):
    pattern = RegularExpressionPattern(r"\[(\d*)\.\.(\d*)\]")


_constraint_list: List[Type[Constraint]] = [
    RangeConstraint,
    MultipleConstraint,
    SetConstraint,
    SelectorConstraint,
    StringPatternConstraint,
    DataElementValueConstraint,
    DataElementValueSubConstraint,
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
        raise Exception(f"No matching constraint for {text} in element {parent_data_element.name}.")
    raise Exception(f"Multiple matches found for constraint, {text}")


# Required


class DataElement:
    pattern = _data_element_names

    def __init__(  # noqa: PLR0912 too-many-branches
        self,
        name: str,
        data_element_dictionary: dict,
        parent_data_group: DataGroup,
    ):
        self.name = name
        self.dictionary = data_element_dictionary
        self.parent_data_group = parent_data_group
        self.constraints: List[Constraint] = []
        self.is_id = False
        # Data Type is required by subsequent attribute processing; e.g. some Constraints
        if "Type" in self.dictionary:
            data_type_str = self.dictionary["Type"]
            if data_type_str == "Numeric":
                if "Units" not in self.dictionary:
                    raise ValueError(
                        f"Units are required for Numeric data type in '"
                        f"{self.parent_data_group.parent_schema.name}.{self.parent_data_group.name}.{self.name}.'"
                    )
            self.data_type = self.get_data_type(data_type_str)
            self._assign_custom_attributes_to_type(data_type_str)
        for attribute in {k: v for k, v in self.dictionary.items() if k not in {"Type"}}:
            if attribute == "Description":
                self.description = self.dictionary[attribute]
            elif attribute == "Units":
                self.units = self.dictionary[attribute]
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
            elif attribute in self.parent_data_group.custom_element_attributes:
                continue
            else:
                raise UnrecognizedAttributeError(
                    f'Unrecognized attribute, "{attribute}". '
                    f"Schema={self.parent_data_group.parent_schema.file_path}, "
                    f"Data Group={self.parent_data_group.name}, "
                    f"Data Element={self.name}",
                    f"{attribute}",
                )

    def get_data_type(self, attribute_str: str) -> DataType:
        """
        Returns the data type from the attribute string.
        """
        try:
            return self.parent_data_group.parent_schema.data_type_factory(attribute_str, self)
        except RuntimeError:
            for reference_schema in self.parent_data_group.parent_schema.reference_schemas.values():
                try:
                    return reference_schema.data_type_factory(attribute_str, self)
                except RuntimeError:
                    continue
        raise RuntimeError  # if you haven't returned a valid DataType by now

    def set_constraints(self, constraints_input: Union[str, List[str]]) -> None:
        if not isinstance(constraints_input, list):
            constraints_input = [constraints_input]

        for constraint in constraints_input:
            self.constraints.append(_constraint_factory(constraint, self))

    def resolve(self):
        self.data_type.resolve()
        for constraint in self.constraints:
            constraint.resolve()

    def _assign_custom_attributes_to_type(self, data_type_str: str) -> None:
        if m := self.data_type.pattern.match(data_type_str):
            try:
                internal_type = m.group("DataGroupName")
                assert self.parent_data_group.parent_schema
                if internal_type in self.parent_data_group.parent_schema.data_groups:
                    self.parent_data_group.parent_schema.data_groups[internal_type].custom_element_attributes.update(
                        self.parent_data_group.custom_element_attributes
                    )
            except IndexError:
                pass


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
        self.parent_template: DataGroupTemplate | None = self._assign_template(
            self.dictionary.get("Data Group Template", "")
        )
        self.data_elements: dict[str, DataElement] = {}
        self.custom_element_attributes: set[str] = (
            self.parent_template.custom_element_attributes if self.parent_template else set()
        )
        self.id_data_element: Union[DataElement, None] = None  # data element containing unique id for this data group
        # for data_element in self.dictionary["Data Elements"]:
        #     self.data_elements[data_element] = DataElement(
        #         data_element, self.dictionary["Data Elements"][data_element], self
        #     )

    def _assign_template(self, template_name: str) -> DataGroupTemplate | None:
        for reference_schema in self.parent_schema.reference_schemas.values():
            if template_name in reference_schema.data_group_templates:
                return reference_schema.data_group_templates[template_name]
        return None

    def resolve(self):
        for data_element in self.data_elements.values():
            data_element.resolve()


class Enumerator:
    pattern = EnumerationType.value_pattern

    def __init__(self, name: str, enumerator_dictionary: dict, parent_enumeration: Enumeration):
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
            self.enumerators[enumerator] = Enumerator(enumerator, self.dictionary["Enumerators"][enumerator], self)


class DataGroupTemplate:
    def __init__(self, name: str, data_group_template_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = data_group_template_dictionary
        self.parent_schema = parent_schema
        # Custom Attributes should eventually be a dictionary
        self.custom_element_attributes: set[str] = set(self.dictionary.get("Custom Attributes", {}).keys())


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

        self.data_group_types = DataGroupType.pattern.cleaned()
        self.enumeration_types = EnumerationType.pattern.cleaned()
        references = ReferenceType.pattern.cleaned()
        single_type = rf"({base_types}|{re_string_types}|{self.data_group_types}|{self.enumeration_types}|{references})"
        alternatives = rf"\(({single_type})(,\s*{single_type})+\)"
        arrays = ArrayType.pattern.cleaned()
        self.data_types = RegularExpressionPattern(f"({single_type})|({alternatives})|({arrays})")

        # Values
        self.values = RegularExpressionPattern(
            f"(({self.numeric})|({self.string})|({self.enumerator})|({self.boolean}))"
        )

        # Constraints
        self.range_constraint = RangeConstraint.pattern.cleaned()
        self.multiple_constraint = MultipleConstraint.pattern.cleaned()
        self.data_element_value_constraint = DataElementValueConstraint.pattern
        self.data_element_value_subconstraint = DataElementValueSubConstraint.pattern
        sets = SetConstraint.pattern.cleaned()
        reference_scope = f":{_type_base_names}:"
        self.selector_constraint = SelectorConstraint.pattern.cleaned()
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


class UnrecognizedAttributeError(Exception):
    def __init__(self, message, attribute_name):
        self.message = message
        self.attribute_name: str = attribute_name
        super().__init__(message)

    def __str__(self):
        return f"{self.message}"


class Schema:
    def __init__(  # noqa: PLR0912 too-many-branches
        self,
        file_path: pathlib.Path,
        parent_schema: Schema | None = None,
    ):
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
                self.data_groups[object_name] = DataGroup(object_name, self.source_dictionary[object_name], self)
            elif object_type == "Enumeration":
                self.enumerations[object_name] = Enumeration(object_name, self.source_dictionary[object_name], self)
            elif object_type == "Type":
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
        for group in self.data_groups.values():
            for data_element in group.dictionary["Data Elements"]:
                group.data_elements[data_element] = DataElement(
                    data_element, group.dictionary["Data Elements"][data_element], group
                )

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
        self.reference_schemas: dict[str, Schema] = {}
        if self.file_path != core_schema_path:
            self.set_reference_schema("core", core_schema_path)
        if "References" in self.source_dictionary["Schema"]:
            parent_directory = self.file_path.parent
            for reference in self.source_dictionary["Schema"]["References"]:
                if reference == "core":
                    raise Exception(f"Illegal reference schema name, {reference}. This name is reserved.")
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
            raise Exception(f'Data Group "{data_group_name}" not found in "{self.file_path}" or its referenced schemas')

        return matching_schemas[0].data_groups[data_group_name]

    def data_type_factory(self, text: str, parent_data_element: DataElement) -> DataType:
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
