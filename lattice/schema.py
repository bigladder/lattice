from __future__ import annotations # Needed for type hinting classes that are not yet fully defined
from .file_io import load, dump, get_file_basename
import pathlib

class DataType:
    def __init__(self, name: str, data_type_dictionary: dict):
        self.name = name
        self.dictionary = data_type_dictionary

class StringType:
    def __init__(self, name: str, string_type_dictionary: dict):
        self.name = name
        self.dictionary = string_type_dictionary

class DataElement:
    def __init__(self, name : str, data_element_dictionary : dict):
        self.name = name
        self.dictionary = data_element_dictionary

class DataGroup:
    def __init__(self, name, data_group_dictionary):
        self.name = name
        self.dictionary = data_group_dictionary
        self.data_elements = []
        for data_element in self.dictionary["Data Elements"]:
            self.data_elements.append(DataElement(data_element, self.dictionary["Data Elements"][data_element]))

class Enumerator:
    def __init__(self, name, enumerator_dictionary) -> None:
        self.name = name
        self.dictionary = enumerator_dictionary

class Enumeration:
    def __init__(self, name, enumeration_dictionary):
        self.name = name
        self.dictionary = enumeration_dictionary
        self.enumerators = []
        for enumerator in self.dictionary["Enumerators"]:
            self.enumerators.append(Enumerator(enumerator, self.dictionary["Enumerators"][enumerator]))

class DataGroupTemplate:
    def __init__(self, name: str, data_group_template_dictionary: dict):
        self.name = name
        self.dictionary = data_group_template_dictionary

class Schema:

    def __init__(self, file_path: pathlib.Path, parent_schema: Schema | None = None):
        self.file_path = file_path
        self.source_dictionary = load(self.file_path)
        if "Schema" not in self.source_dictionary:
            raise Exception(f"\"Schema\" node not found in {self.file_path}")

        self.parent_schema = parent_schema
        self.data_types = []
        self.string_types = []
        self.enumerations = []
        self.data_groups = []
        self.data_group_templates = []

        for object_name in self.source_dictionary:
            if object_name == "Schema":
              self.title = self.source_dictionary[object_name]["Title"]
              self.description = self.source_dictionary[object_name]["Version"]
              self.version = self.source_dictionary[object_name]["Version"]
              self.root_data_group = self.source_dictionary[object_name]["Root Data Group"] if "Root Data Group" in self.source_dictionary["Schema"] else None
              self.process_references()
            else:
                object_type = self.source_dictionary[object_name]["Object Type"]
                if object_type == "Data Group":
                    self.data_groups.append(DataGroup(object_name, self.source_dictionary[object_name]))
                elif object_type == "Enumeration":
                    self.enumerations.append(Enumeration(object_name, self.source_dictionary[object_name]))
                elif object_type == "Data Type":
                    self.data_types.append(DataType(object_name, self.source_dictionary[object_name]))
                elif object_type == "String Type":
                    self.data_types.append(StringType(object_name, self.source_dictionary[object_name]))
                elif object_type == "Data Group Template":
                    self.data_types.append(DataGroupTemplate(object_name, self.source_dictionary[object_name]))
                else:
                    raise Exception(f"Unrecognized Object Type, \"{object_type}\" in {self.file_path}")

    def process_references(self):
        # TODO: reference existing schemas instead of making new ones
        self.reference_schemas : list(Schema) = []
        core_schema_path = pathlib.Path(pathlib.Path(__file__).parent,"core.schema.yaml")
        if self.file_path != core_schema_path:
            self.reference_schemas.append(Schema(core_schema_path,self))
        if "References" in self.source_dictionary["Schema"]:
            parent_directory = self.file_path.parent
            for reference in self.source_dictionary["Schema"]["References"]:
                self.reference_schemas.append(Schema(pathlib.Path(parent_directory,f"{reference}.schema.yaml"),self))
