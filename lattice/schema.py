from __future__ import annotations # Needed for type hinting classes that are not yet fully defined
from .file_io import load, dump, get_file_basename
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


class SchemaPatterns:

    number = RegularExpressionPattern("([-+]?[0-9]*\\.?[0-9]+([eE][-+]?[0-9]+)?)")
    integer = RegularExpressionPattern("([-+]?[0-9]+)")
    string = RegularExpressionPattern("\".*\"")
    enumerator = RegularExpressionPattern("([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*")
    boolean = RegularExpressionPattern("True|False")

    type_base_names = RegularExpressionPattern("[A-Z]([A-Z]|[a-z]|[0-9])*")
    data_group_names = type_base_names
    enumeration_names = type_base_names
    data_element_names = RegularExpressionPattern("([a-z][a-z,0-9]*)(_([a-z,0-9])+)*")

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

        self.data_group_types = RegularExpressionPattern(fr"\{{{self.data_group_names}\}}")
        self.enumeration_types = RegularExpressionPattern(fr"<{self.enumeration_names}>")
        self.optional_base_types = fr"{base_types}{{1}}(\/{base_types})*"
        single_type = fr"({self.optional_base_types}|{re_string_types}|{self.data_group_types}|{self.enumeration_types})"
        alternatives = fr"\(({single_type})(,\s*{single_type})+\)"
        arrays = fr"\[({single_type})\](\[\d*\.*\d*\])?"
        self.data_types = RegularExpressionPattern(f"({single_type})|({alternatives})|({arrays})")

        # Values
        self.values = RegularExpressionPattern(f"(({self.number})|({self.string})|({self.enumerator})|({self.boolean}))")

        # Constraints
        alpha_array = "(\[A-Z\]{[1-9]+})"
        numeric_array = "(\[0-9\]{[1-9]+})"
        self.range_constraint = RegularExpressionPattern(f"(>|>=|<=|<){self.number}")
        self.multiple_constraint = RegularExpressionPattern(f"%{self.number}")
        self.data_element_value_constraint = RegularExpressionPattern(f"({self.data_element_names})=({self.values})")
        sets = f"\[{self.number}(, {self.number})*\]"
        reference_scope = f":{self.type_base_names}:"
        self.selector_constraint = RegularExpressionPattern(fr"{self.data_element_names}\({self.enumerator}(,\s*{self.enumerator})*\)")

        self.constraints = RegularExpressionPattern(f"({alpha_array}|{numeric_array}|{self.range_constraint})|({self.multiple_constraint})|({sets})|({self.data_element_value_constraint})|({reference_scope})|({self.selector_constraint})")

        # Conditional Requirements
        self.conditional_requirements = RegularExpressionPattern(f"if (!?{self.data_element_names})(!?=({self.values}))?")

class DataType:
    def __init__(self, name: str, data_type_dictionary: dict):
        self.name = name
        self.dictionary = data_type_dictionary

class StringType:
    def __init__(self, name: str, string_type_dictionary: dict):
        self.name = name
        self.dictionary = string_type_dictionary


class Constraint:
    def __init__(self, text: str, parent_data_element: DataElement):
        self.text = text
        self.parent_data_element = parent_data_element

class RangeConstraint(Constraint):
    def __init__(self, text: str, parent_data_element: DataElement):
        Constraint.__init__(self, text, parent_data_element)

class MultipleConstraint(Constraint):
    def __init__(self, text: str, parent_data_element: DataElement):
        Constraint.__init__(self, text, parent_data_element)

class SetConstraint(Constraint):
    def __init__(self, text: str, parent_data_element: DataElement):
        Constraint.__init__(self, text, parent_data_element)

class SelectorConstraint(Constraint):
    def __init__(self, text: str, parent_data_element: DataElement):
        Constraint.__init__(self, text, parent_data_element)

class StringPatternConstraint(Constraint):
    def __init__(self, text: str, parent_data_element: DataElement):
        Constraint.__init__(self, text, parent_data_element)

class DataElementValueConstraint(Constraint):
    def __init__(self, text: str, parent_data_element: DataElement):
        Constraint.__init__(self, text, parent_data_element)
        self.pattern = parent_data_element.parent_data_group.parent_schema.schema_patterns.data_element_value_constraint
        match = self.pattern.match(self.text)
        self.data_element_name = match.group(1)
        self.data_element_value = match.group(5)


class ArrayLengthLimitsConstraint(Constraint):
    def __init__(self, text: str, parent_data_element: DataElement):
        Constraint.__init__(self, text, parent_data_element)



class DataElement:
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
                self.data_type_string = self.dictionary[attribute]
                # TODO: type specific characteristics
            elif attribute == "Constraints":
                self.process_constraints(self.dictionary[attribute])
            elif attribute == "Required":
                self.required = self.dictionary[attribute]
            elif attribute == "Notes":
                self.notes = self.dictionary[attribute]
            else:
                raise Exception(f"Unrecognized attribute, \"{attribute}\". Schema={self.parent_data_group.parent_schema.file_path}, Data Group={self.parent_data_group.name}, Data Element={self.name}")

    def process_constraints(self, constraints_input):
        schema_patterns = self.parent_data_group.parent_schema.schema_patterns
        if type(constraints_input) is not list:
            constraints_input = [constraints_input]

        for constraint in constraints_input:
            data_element_value_match = schema_patterns.data_element_value_constraint.match(constraint)
            ranges_match = schema_patterns.range_constraint.match(constraint)
            multiple_match = schema_patterns.multiple_constraint.match(constraint)
            selector_match = schema_patterns.selector_constraint.match(constraint)
            if data_element_value_match:
                self.constraints.append(DataElementValueConstraint(constraint, self))
            elif ranges_match:
                self.constraints.append(RangeConstraint(constraint, self))
            elif multiple_match:
                self.constraints.append(MultipleConstraint(constraint, self))
            elif selector_match:
                self.constraints.append(SelectorConstraint(constraint, self))
            else:
                raise Exception(f"Unrecognized constraint syntax, \"{constraint}\"")
                self.constraints.append(Constraint(constraint, self))

class DataGroup:
    def __init__(self, name, data_group_dictionary, parent_schema : Schema):
        self.name = name
        self.dictionary = data_group_dictionary
        self.parent_schema = parent_schema
        self.data_elements = {}
        for data_element in self.dictionary["Data Elements"]:
            self.data_elements[data_element] = DataElement(data_element, self.dictionary["Data Elements"][data_element], self)

class Enumerator:
    def __init__(self, name, enumerator_dictionary) -> None:
        self.name = name
        self.dictionary = enumerator_dictionary

class Enumeration:
    def __init__(self, name, enumeration_dictionary):
        self.name = name
        self.dictionary = enumeration_dictionary
        self.enumerators = {}
        for enumerator in self.dictionary["Enumerators"]:
            self.enumerators[enumerator] = Enumerator(enumerator, self.dictionary["Enumerators"][enumerator])

class DataGroupTemplate:
    def __init__(self, name: str, data_group_template_dictionary: dict):
        self.name = name
        self.dictionary = data_group_template_dictionary

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

        self.schema_patterns = SchemaPatterns(self.source_dictionary)

        for object_name in self.source_dictionary:
            if object_name == "Schema":
              self.title = self.source_dictionary[object_name]["Title"]
              self.description = self.source_dictionary[object_name]["Version"]
              self.version = self.source_dictionary[object_name]["Version"]
              self.root_data_group_name = self.source_dictionary[object_name]["Root Data Group"] if "Root Data Group" in self.source_dictionary["Schema"] else None
              self.process_references()
            else:
                object_type = self.source_dictionary[object_name]["Object Type"]
                if object_type == "Data Group":
                    self.data_groups[object_name] = DataGroup(object_name, self.source_dictionary[object_name], self)
                elif object_type == "Enumeration":
                    self.enumerations[object_name] = Enumeration(object_name, self.source_dictionary[object_name])
                elif object_type == "Data Type":
                    self.data_types[object_name] = DataType(object_name, self.source_dictionary[object_name])
                elif object_type == "String Type":
                    self.data_types[object_name] = StringType(object_name, self.source_dictionary[object_name])
                elif object_type == "Data Group Template":
                    self.data_types[object_name] = DataGroupTemplate(object_name, self.source_dictionary[object_name])
                else:
                    raise Exception(f"Unrecognized Object Type, \"{object_type}\" in {self.file_path}")

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

    def process_references(self):
        # TODO: reference existing schemas instead of making new ones
        self.reference_schemas = {}
        if self.file_path != core_schema_path:
            self.reference_schemas["core"] = Schema(core_schema_path,self)
        if "References" in self.source_dictionary["Schema"]:
            parent_directory = self.file_path.parent
            for reference in self.source_dictionary["Schema"]["References"]:
                self.reference_schemas[reference] = Schema(pathlib.Path(parent_directory,f"{reference}.schema.yaml"),self)

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



def get_types(schema):
    '''For each Object Type in a schema, map a list of Objects matching that type.'''
    types = {}
    for object in schema:
        if schema[object]["Object Type"] not in types:
            types[schema[object]["Object Type"]] = []
        types[schema[object]["Object Type"]].append(object)
    return types
