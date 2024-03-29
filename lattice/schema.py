from __future__ import annotations # Needed for type hinting classes that are not yet fully defined
from .file_io import load, get_file_basename
import pathlib
import re

core_schema_path = pathlib.Path(pathlib.Path(__file__).parent,"core.schema.yaml")

class RegularExpressionPattern:
    def __init__(self, pattern_string: str) -> None:
        self.pattern = re.compile(pattern_string)
        self.anchored_pattern = re.compile(self.anchor(pattern_string))

    def __str__(self):
        return self.pattern.pattern

    def match(self, test_string: str, anchored: bool = False):
        return self.pattern.match(test_string) if not anchored else self.anchored_pattern.match(test_string)

    def anchored(self):
        return self.anchored_pattern.pattern

    @staticmethod
    def anchor(pattern_text: str):
        return f"^{pattern_text}$"

# Attributes

# Data Types
_type_base_names = RegularExpressionPattern("[A-Z]([A-Z]|[a-z]|[0-9])*")
_data_element_names = RegularExpressionPattern("([a-z][a-z,0-9]*)(_([a-z,0-9])+)*")

class DataType:
    def __init__(self, text, parent_data_element: DataElement):
        self.text = text
        self.parent_data_element = parent_data_element

    def get_path(self) -> str:
        return f"{self.parent_data_element.parent_data_group.parent_schema.name}.{self.parent_data_element.parent_data_group.name}.{self.parent_data_element.name}.Data Type"

    def resolve(self):
        pass

class IntegerType(DataType):
    pattern = RegularExpressionPattern("(Integer)")
    value_pattern = RegularExpressionPattern("([-+]?[0-9]+)")
    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)

class NumericType(DataType):
    pattern = RegularExpressionPattern("(Numeric)")
    value_pattern = RegularExpressionPattern("([-+]?[0-9]*\\.?[0-9]+([eE][-+]?[0-9]+)?)")
    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)

class BooleanType(DataType):
    pattern = RegularExpressionPattern("(Boolean)")
    value_pattern = RegularExpressionPattern("True|False")
    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)

class StringType(DataType):
    pattern = RegularExpressionPattern("(String)")
    value_pattern = RegularExpressionPattern("\".*\"")
    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)

class PatternType(DataType):
    pattern = RegularExpressionPattern("(Pattern)")
    value_pattern = RegularExpressionPattern("\".*\"")
    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)

class ArrayType(DataType):
    pattern = RegularExpressionPattern(fr"\[(\S+)]")
    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)

class DataGroupType(DataType):
    pattern = RegularExpressionPattern(fr"\{{({_type_base_names})\}}")
    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)
        self.data_group_name = self.pattern.match(text).group(1)

    def resolve(self):
        self.data_group = self.parent_data_element.parent_data_group.parent_schema.get_data_group(self.data_group_name)

class EnumerationType(DataType):
    pattern = RegularExpressionPattern(fr"<{_type_base_names}>")
    value_pattern = RegularExpressionPattern("([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*")
    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)

class AlternativeType(DataType):
    pattern = RegularExpressionPattern(fr"\(([^\s,]+)((, ?([^\s,]+))+)\)")
    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)

_value_pattern = RegularExpressionPattern(f"(({NumericType.value_pattern})|({StringType.value_pattern})|({EnumerationType.value_pattern})|({BooleanType.value_pattern}))")

# Constraints
class Constraint:
    def __init__(self, text: str, parent_data_element: DataElement):
        self.text = text
        self.parent_data_element = parent_data_element

class RangeConstraint(Constraint):
    pattern = RegularExpressionPattern(f"(>|>=|<=|<)({NumericType.value_pattern})")
    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)

class MultipleConstraint(Constraint):
    pattern = RegularExpressionPattern(f"%({NumericType.value_pattern})")
    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)

class SetConstraint(Constraint):
    pattern = RegularExpressionPattern(f"\[{NumericType.value_pattern}(, ?{NumericType.value_pattern})*\]")
    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(self, text, parent_data_element)

class SelectorConstraint(Constraint):
    pattern = RegularExpressionPattern(fr"{_data_element_names}\({EnumerationType.value_pattern}(, ?{EnumerationType.value_pattern})*\)")
    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)

class StringPatternConstraint(Constraint):
    pattern = RegularExpressionPattern("\".*\"")
    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(self, text, parent_data_element)
        try:
            re.compile(text)
        except:
            raise Exception(f"Invalid regular expression: {text}")

class DataElementValueConstraint(Constraint):
    pattern = RegularExpressionPattern(f"({_data_element_names})=({_value_pattern})")
    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)
        self.pattern = parent_data_element.parent_data_group.parent_schema.schema_patterns.data_element_value_constraint
        match = self.pattern.match(self.text)
        self.data_element_name = match.group(1) # TODO: Named groups?
        self.data_element_value = match.group(5) # TODO: Named groups?

class ArrayLengthLimitsConstraint(Constraint):
    pattern = RegularExpressionPattern(f"\[(\d*)\.\.(\d*)\]")
    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(self, text, parent_data_element)

_constraint_list = [
    RangeConstraint,
    MultipleConstraint,
    SetConstraint,
    SelectorConstraint,
    StringPatternConstraint,
    DataElementValueConstraint,
    ArrayLengthLimitsConstraint
]

def _constraint_factory(input: str, parent_data_element: DataElement):
    number_of_matches = 0
    match_type = None
    for constraint in _constraint_list:
        if constraint.pattern.match(input):
            match_type = constraint
            number_of_matches += 1

    if number_of_matches == 1:
        return match_type(input, parent_data_element)
    elif number_of_matches == 0:
        raise Exception(f"No matching constraint for {input}.")
    else:
        raise Exception(f"Multiple matches found for constraint, {input}")

# Required

class DataElement:
    pattern = _data_element_names
    def __init__(self, name : str, data_element_dictionary : dict, parent_data_group : DataGroup):
        self.name = name
        self.dictionary = data_element_dictionary
        self.parent_data_group = parent_data_group
        self.constraints = []
        for attribute in self.dictionary:
            if attribute == "Description":
                self.description = self.dictionary[attribute]
            elif attribute == "Units":
                self.units = self.dictionary[attribute]
            elif attribute == "Data Type":
                self.data_type = self.parent_data_group.parent_schema.data_type_factory(self.dictionary[attribute], self)
            elif attribute == "Constraints":
                self.set_constraints(self.dictionary[attribute])
            elif attribute == "Required":
                self.required = self.dictionary[attribute]
            elif attribute == "Notes":
                self.notes = self.dictionary[attribute]
            else:
                raise Exception(f"Unrecognized attribute, \"{attribute}\". Schema={self.parent_data_group.parent_schema.file_path}, Data Group={self.parent_data_group.name}, Data Element={self.name}")

    def set_constraints(self, constraints_input):
        if type(constraints_input) is not list:
            constraints_input = [constraints_input]

        for constraint in constraints_input:
            self.constraints.append(_constraint_factory(constraint, self))

    def resolve(self):
        self.data_type.resolve()

class FundamentalDataType:
    def __init__(self, name: str, data_type_dictionary: dict, parent_schema : Schema):
        self.name = name
        self.dictionary = data_type_dictionary
        self.parent_schema = parent_schema

class CommonStringType:
    def __init__(self, name: str, string_type_dictionary: dict, parent_schema : Schema):
        self.name = name
        self.dictionary = string_type_dictionary
        self.parent_schema = parent_schema
        self.value_pattern = self.dictionary["JSON Schema Pattern"]

        # Make new DataType class
        def init_method(self, text, parent_data_element):
            StringType.__init__(self, text, parent_data_element)

        self.data_type_class = type(self.name, (StringType, ), {
            "__init__": init_method,
            "pattern": RegularExpressionPattern(self.name),
            "value_pattern": RegularExpressionPattern(self.value_pattern),
        })

        parent_schema.add_data_type(self.data_type_class)

class DataGroup:
    def __init__(self, name, data_group_dictionary, parent_schema : Schema):
        self.name = name
        self.dictionary = data_group_dictionary
        self.parent_schema = parent_schema
        self.data_elements = {}
        for data_element in self.dictionary["Data Elements"]:
            self.data_elements[data_element] = DataElement(data_element, self.dictionary["Data Elements"][data_element], self)

    def resolve(self):
        for data_element in self.data_elements.values():
            data_element.resolve()

class Enumerator:
    pattern = EnumerationType.value_pattern
    def __init__(self, name, enumerator_dictionary, parent_enumeration : Enumeration) -> None:
        self.name = name
        self.dictionary = enumerator_dictionary
        self.parent_enumeration = parent_enumeration

class Enumeration:
    def __init__(self, name, enumeration_dictionary, parent_schema : Schema):
        self.name = name
        self.dictionary = enumeration_dictionary
        self.parent_schema = parent_schema
        self.enumerators = {}
        for enumerator in self.dictionary["Enumerators"]:
            self.enumerators[enumerator] = Enumerator(enumerator, self.dictionary["Enumerators"][enumerator], self)

class DataGroupTemplate:
    def __init__(self, name: str, data_group_template_dictionary: dict, parent_schema : Schema):
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

        base_types = '|'.join(regex_base_types)
        base_types = RegularExpressionPattern(f"({base_types})")

        string_types = core_types["String Type"]
        if schema:
            schema_types = get_types(schema)
            self.combined_types |= set(schema_types.keys())
            if "String Type" in schema_types:
                string_types += ["String Type"]

        re_string_types = '|'.join(string_types)
        re_string_types = RegularExpressionPattern(f"({re_string_types})")

        self.data_group_types = DataGroupType.pattern
        self.enumeration_types = EnumerationType.pattern
        single_type = fr"({base_types}|{re_string_types}|{self.data_group_types}|{self.enumeration_types})"
        alternatives = fr"\(({single_type})(,\s*{single_type})+\)"
        arrays = fr"\[({single_type})\](\[\d*\.*\d*\])?"
        self.data_types = RegularExpressionPattern(f"({single_type})|({alternatives})|({arrays})")

        # Values
        self.values = RegularExpressionPattern(f"(({self.numeric})|({self.string})|({self.enumerator})|({self.boolean}))")

        # Constraints
        alpha_array = "(\[A-Z\]{[1-9]+})"
        numeric_array = "(\[0-9\]{[1-9]+})"
        self.range_constraint = RangeConstraint.pattern
        self.multiple_constraint = MultipleConstraint.pattern
        self.data_element_value_constraint = DataElementValueConstraint.pattern
        sets = SetConstraint.pattern
        reference_scope = f":{_type_base_names}:"
        self.selector_constraint = SelectorConstraint.pattern

        self.constraints = RegularExpressionPattern(f"({alpha_array}|{numeric_array}|{self.range_constraint})|({self.multiple_constraint})|({sets})|({self.data_element_value_constraint})|({reference_scope})|({self.selector_constraint})")

        # Conditional Requirements
        self.conditional_requirements = RegularExpressionPattern(f"if (!?{self.data_element_names})(!?=({self.values}))?")



class Schema:

    def __init__(self, file_path: pathlib.Path, parent_schema: Schema | None = None):
        self.file_path = file_path.absolute()
        self.source_dictionary = load(self.file_path)
        self.name = get_file_basename(self.file_path, depth=2)
        if "Schema" not in self.source_dictionary:
            raise Exception(f"\"Schema\" node not found in {self.file_path}")

        self.parent_schema = parent_schema
        self.data_types = {}
        self.string_types = {}
        self.enumerations = {}
        self.data_groups = {}
        self.data_group_templates = {}

        self._data_type_list = [
            IntegerType,
            NumericType,
            BooleanType,
            StringType,
            PatternType,
            ArrayType,
            DataGroupType,
            EnumerationType,
            AlternativeType
        ]

        self.schema_patterns = SchemaPatterns(self.source_dictionary)

        if "Schema" in self.source_dictionary:
            self.title = self.source_dictionary["Schema"]["Title"]
            self.description = self.source_dictionary["Schema"]["Description"]
            self.version = self.source_dictionary["Schema"]["Version"]
            self.root_data_group_name = self.source_dictionary["Schema"]["Root Data Group"] if "Root Data Group" in self.source_dictionary["Schema"] else None
            self.set_reference_schemas()

        for object_name in self.source_dictionary:
            object_type = self.source_dictionary[object_name]["Object Type"]
            if object_type == "Data Group":
                self.data_groups[object_name] = DataGroup(object_name, self.source_dictionary[object_name], self)
            elif object_type == "Enumeration":
                self.enumerations[object_name] = Enumeration(object_name, self.source_dictionary[object_name], self)
            elif object_type == "Data Type":
                self.data_types[object_name] = FundamentalDataType(object_name, self.source_dictionary[object_name], self)
            elif object_type == "String Type":
                self.data_types[object_name] = CommonStringType(object_name, self.source_dictionary[object_name], self)
            elif object_type == "Data Group Template":
                self.data_types[object_name] = DataGroupTemplate(object_name, self.source_dictionary[object_name], self)
        #    else:
        #        raise Exception(f"Unrecognized Object Type, \"{object_type}\" in {self.file_path}")

        # Get top level info
        self.root_data_group = None
        self.metadata = None
        self.schema_author = None
        self.schema_type = self.name

        if self.root_data_group_name is not None:
            self.schema_type = self.root_data_group_name
            self.root_data_group = self.get_data_group(self.root_data_group_name)
            self.metadata = self.root_data_group.data_elements["metadata"] if "metadata" in self.root_data_group.data_elements else None
            if self.metadata is not None:
                for constraint in self.metadata.constraints:
                    if type(constraint) is DataElementValueConstraint:
                        if constraint.data_element_name == "schema_author":
                            self.schema_author = constraint.data_element_value
                        elif constraint.data_element_name == "schema":
                            self.schema_type = constraint.data_element_value

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
                    raise Exception(f"Illegal reference schema name, {reference}. This name is reserved.")
                self.set_reference_schema(reference, pathlib.Path(parent_directory,f"{reference}.schema.yaml"))

    def set_reference_schema(self, schema_name, schema_path):
        existing_schema = self.get_reference_schema(schema_name)

        if existing_schema is not None:
            self.reference_schemas[schema_name] = existing_schema
        else:
            self.reference_schemas[schema_name] = Schema(schema_path, self)

    def get_reference_schema(self, schema_name) -> Schema|None:
        # TODO: verify schema has the same path too?
        # Search this schema first
        if schema_name in self.reference_schemas:
            return self.reference_schemas[schema_name]

        # Search parent schema
        if self.parent_schema is not None:
            return self.parent_schema.get_reference_schema(schema_name)

        return None

    def get_data_group(self, data_group_name: str):
        matching_schemas = []
        # 1. Search this schema first
        if data_group_name in self.data_groups:
            matching_schemas.append(self)
        for reference_schema in self.reference_schemas.values():
            if data_group_name in reference_schema.data_groups:
                matching_schemas.append(reference_schema)

        if len(matching_schemas) == 0:
            raise Exception(f"Data Group \"{data_group_name}\" not found in \"{self.file_path}\" or its referenced schemas")

        return matching_schemas[0].data_groups[data_group_name]

    def data_type_factory(self, input: str, parent_data_element: DataElement) -> DataType:
        number_of_matches = 0
        match_type = None
        for data_type in self._data_type_list:
            if data_type.pattern.match(input):
                match_type = data_type
                number_of_matches += 1

        if number_of_matches == 1:
            return match_type(input, parent_data_element)
        elif number_of_matches == 0:
            raise Exception(f"No matching data type for {input}.")
        else:
            raise Exception(f"Multiple matches found for data type, {input}")

    def add_data_type(self, data_type: DataType):
        if data_type not in self._data_type_list:
            self._data_type_list.append(data_type)

        if self.parent_schema is not None:
            self.parent_schema.add_data_type(data_type)


def get_types(schema):
    '''For each Object Type in a schema, map a list of Objects matching that type.'''
    types = {}
    for object in schema:
        if schema[object]["Object Type"] not in types:
            types[schema[object]["Object Type"]] = []
        types[schema[object]["Object Type"]].append(object)
    return types
