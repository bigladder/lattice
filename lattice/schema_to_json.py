"""This module encapsulates JSON translation and validation functions for YAML source schema"""

import os
import re
import warnings
from pathlib import Path
from typing import Optional

from .file_io import dump, get_base_stem, load
from .meta_schema import MetaSchema

# 'once': Suppress multiple warnings from the same location.
# 'always': Show all warnings
# 'ignore': Show no warnings
warnings.simplefilter("always", UserWarning)


# -------------------------------------------------------------------------------------------------
class DataGroup:  # pylint: disable=R0903
    """Class to convert source schema Data Group Objects into JSON"""

    # The following regular expressions are explicity not Unicode
    array_type = r"^\[(?P<array_of>.*?)\]"  # Array of type 'Type' e.g. '[Type]'
    # just the first [] pair; using non-greedy '?'
    alternative_type = r"^\((?P<one_of>.*)\)"  # Parentheses encapsulate a list of options
    # Parse ellipsis range-notation e.g. '[1..]'
    minmax_range_type = r"(?P<min>[0-9]*)(?P<ellipsis>\.*)(?P<max>[0-9]*)"

    enum_or_def = r"(\{|\<|:)(.*)(\}|\>|:)"
    numeric_type = r"[+-]?[0-9]*\.?[0-9]+|[0-9]+"  # Any optionally signed, floating point number
    scope_constraint = r"^:(?P<scope>.*):"  # Lattice scope constraint for ID/Reference
    ranged_array_type = rf"{array_type}(\[{minmax_range_type}\])?"

    def __init__(self, name, type_list, ref_list):
        self._name = name
        self._types = type_list
        self._refs = ref_list
        self._match_types = re.compile(
            f"(?P<ranged_array>{DataGroup.ranged_array_type})|({DataGroup.alternative_type})"
        )

    def add_data_group(self, group_name, group_subdict):
        """
        Process Data Group from the source schema into a properties node in json.

        :param group_name:      Data Group name; this will become a schema definition key
        :param group_subdict:   Dictionary of Data Elements where each element is a key
        """
        elements = {"type": "object", "properties": {}}
        required = []
        dependencies = {}
        for e in group_subdict:
            element = group_subdict[e]
            if "Description" in element:
                elements["properties"][e] = {"description": element["Description"]}
            if "Data Type" in element:
                try:
                    self._create_type_entry(group_subdict[e], elements, e)
                except RuntimeError as r:
                    raise r
            if "Units" in element:
                elements["properties"][e]["units"] = element["Units"]
            if "Notes" in element:
                elements["properties"][e]["notes"] = element["Notes"]
            if "Required" in element:
                req = element["Required"]
                if isinstance(req, bool):
                    if req is True:
                        required.append(e)
                elif req.startswith("if"):
                    DataGroup._construct_requirement_if_then(elements, dependencies, req[3:], e)
        if required:
            elements["required"] = required
        if dependencies:
            elements["dependencies"] = dependencies
        elements["additionalProperties"] = False
        return {group_name: elements}

    def _create_type_entry(self, parent_dict, target_dict, entry_name):
        """
        Create json type node and its nested nodes if necessary.
        :param parent_dict:     A Data Element's subdictionary, from source schema
        :param target_dict:     The json definition node that will be populated
        :param entry_name:      Data Element name
        """
        if entry_name not in target_dict["properties"]:
            target_dict["properties"][entry_name] = {}
        target_property_entry = target_dict["properties"][entry_name]

        matches = self._match_types.match(parent_dict["Data Type"])
        if matches:
            if matches.group("ranged_array"):
                self._populate_array_type(parent_dict, target_property_entry, matches)
            elif matches.group("one_of"):
                self._populate_selector_types(parent_dict, target_property_entry, matches, entry_name)
        elif parent_dict["Data Type"] in ["ID", "Reference"]:
            try:
                m = re.match(DataGroup.scope_constraint, parent_dict["Constraints"])
                if m:
                    target_property_entry["scopedType"] = parent_dict["Data Type"]
                    target_property_entry["scope"] = m.group("scope")
                    self._get_simple_type(parent_dict["Data Type"], target_property_entry)
            except KeyError:
                raise RuntimeError(f'"Constraints" key does not exist for Data Element "{entry_name}".') from None
        else:
            # 1. 'type' entry
            try:
                self._get_simple_type(parent_dict["Data Type"], target_property_entry)
            except KeyError as e:
                raise RuntimeError from e
            # 2. string pattern or 'm[in/ax]imum' entry
            DataGroup._get_pattern_constraints(parent_dict.get("Constraints"), target_property_entry)
            DataGroup._get_numeric_constraints(parent_dict.get("Constraints"), target_property_entry)

    def _populate_array_type(self, parent_dict, target_entry, matches):
        """
        Decompose an array regex into its dictionary components

        :param parent_dict:  Dict representing schema component
        :param target_entry: Top level JSON describing the component
        :param matches:      Match object for a ranged_array regex
        """
        # 1. 'type' entry
        target_entry["type"] = "array"
        # 2. 'm[in/ax]Items' entry
        if matches.group("min"):
            # Parse ellipsis range-notation e.g. '[1..]'
            target_entry["minItems"] = int(matches.group("min"))
            if matches.group("ellipsis") and matches.group("max"):
                target_entry["maxItems"] = int(matches.group("max"))
            elif not matches.group("ellipsis"):
                target_entry["maxItems"] = int(matches.group("min"))
        # 3. 'items' entry
        target_entry["items"] = {}
        if matches.group("array_of"):
            self._get_simple_type(matches.group("array_of"), target_entry["items"])
            DataGroup._get_pattern_constraints(parent_dict.get("Constraints"), target_entry["items"])
            DataGroup._get_numeric_constraints(parent_dict.get("Constraints"), target_entry["items"])

    def _populate_selector_types(self, parent_dict, target_entry, matches, entry_name):
        """
        Set up selector constraint as a JSON conditional

        :param parent_dict:  Dict representing schema component
        :param target_entry: Top level JSON describing the component
        :param matches:      Match object for a one_of regex
        :param entry_name:   Data Element name
        """
        types = [t.strip() for t in matches.group("one_of").split(",")]
        selection_key, selections = parent_dict["Constraints"].split("(")
        if target_entry.get("allOf") is None:
            target_entry["allOf"] = []
        for s, t in list(zip(selections.split(","), types)):
            target_entry["allOf"].append({})
            DataGroup._construct_selection_if_then(target_entry["allOf"][-1], selection_key, s, entry_name)
            try:
                self._get_simple_type(t, target_entry["allOf"][-1]["then"]["properties"][entry_name])
            except KeyError as e:
                raise RuntimeError from e

    def _get_simple_type(self, type_str, target_dict_to_append):
        """
        Return the internal type described by type_str, along with its json-appropriate key.
        First, attempt to capture enum, definition, or special string types as references;
        then default to fundamental types with simple json key "type".

        :param type_str:                Input string from source schema's Data Type key
        :param target_dict_to_append:   The json "items" node
        """
        internal_type = None
        m = re.match(DataGroup.enum_or_def, type_str)
        if m:
            internal_type = m.group(2)
        else:
            internal_type = type_str
        # Look through the references to assign a source to the type
        for key in self._refs:
            if internal_type in self._refs[key]:
                internal_type = key + ".schema.json#/definitions/" + internal_type
                target_dict_to_append["$ref"] = internal_type
                return
        try:
            target_dict_to_append["type"] = self._types[type_str]
        except KeyError:
            raise KeyError(
                f"Unknown type: {type_str} does not appear in referenced schema "
                f"{list(self._refs.keys())} or type map {self._types}"
            ) from None
        return

    @staticmethod
    def _get_pattern_constraints(constraints_str, target_dict):
        """
        Process alpha/pattern Constraint into pattern field.

        :param constraints_str:     Raw numerical limits and/or multiple information
        :param target_dict:         json property node
        """
        if constraints_str is not None and "type" in target_dict and isinstance(constraints_str, str):
            if "string" in target_dict["type"]:  # String pattern match
                target_dict["pattern"] = constraints_str.replace('"', "")

    @staticmethod
    def _get_numeric_constraints(constraints_str, target_dict):
        """
        Process numeric Constraints into fields.

        :param constraints_str:     Raw numerical limits and/or multiple information
        :param target_dict:         json property node
        """
        if constraints_str is not None:
            constraints = constraints_str if isinstance(constraints_str, list) else [constraints_str]
            minimum = None
            maximum = None
            for c in constraints:
                try:
                    # Process numeric constraints
                    numerical_value = re.findall(DataGroup.numeric_type, c)[0]
                    if ">" in c:
                        minimum = float(numerical_value) if "number" in target_dict["type"] else int(numerical_value)
                        mn = "exclusiveMinimum" if "=" not in c else "minimum"
                        target_dict[mn] = minimum
                    elif "<" in c:
                        maximum = float(numerical_value) if "number" in target_dict["type"] else int(numerical_value)
                        mx = "exclusiveMaximum" if "=" not in c else "maximum"
                        target_dict[mx] = maximum
                    elif "%" in c:
                        target_dict["multipleOf"] = int(numerical_value)
                except IndexError:
                    pass
                except ValueError:
                    pass
                except KeyError:
                    # 'type' not in dictionary
                    pass

    @staticmethod
    def _construct_selection_if_then(target_dict_to_append, selector, selection, entry_name):
        """
        Construct paired if-then json entries for allOf collections translated from source-schema
        "selector" Constraints.

        :param target_dict_to_append:   This dictionary is modified in-situ with an if key and
                                        associated then key
        :param selector:                Constraints key
        :param selection:               Item from constraints values list.
        :param entry_name:              Data Element for which the Data Type must match the
                                        Constraint
        """
        target_dict_to_append["if"] = {
            "properties": {selector: {"const": "".join(ch for ch in selection if ch.isalnum())}}
        }
        target_dict_to_append["then"] = {"properties": {entry_name: {}}}

    @staticmethod
    def _construct_requirement_if_then(
        conditionals_list: dict,
        dependencies_list: dict,
        requirement_str: str,
        requirement: str,
    ):
        """
        Construct paired if-then json entries for conditional requirements.

        :param requirement_str:         Raw requirement string using A232 syntax
        :param requirement:             This item's presence is dependent on the above condition
        """
        separator = r"\sand\s"
        # collector = "allOf"
        selector_dict: dict = {"properties": {}}
        requirement_list = re.split(separator, requirement_str)
        # pylint: disable-next=line-too-long
        dependent_req = r"(?P<selector>!?[0-9a-zA-Z_]*)((?P<is_equal>!?=)(?P<selector_state>[0-9a-zA-Z_]*))?"

        for req in requirement_list:
            m = re.match(dependent_req, req)
            if m:
                selector = m.group("selector")
                if m.group("is_equal"):
                    is_equal = "!" not in m.group("is_equal")
                    selector_state = m.group("selector_state")
                    if "true" in selector_state.lower():
                        selector_state = True
                    elif "false" in selector_state.lower():
                        selector_state = False
                    selector_dict["properties"][selector] = (
                        {"const": selector_state} if is_equal else {"not": {"const": selector_state}}
                    )
                elif dependencies_list.get(selector):
                    dependencies_list[selector].append(requirement)
                elif "!" in selector:
                    dependencies_list[selector.lstrip("!")] = {"not": {"required": [requirement]}}
                else:
                    dependencies_list[selector] = [requirement]

        if selector_dict["properties"].keys():
            # Conditional requirements are each a member of a list
            if conditionals_list.get("allOf") is None:
                conditionals_list["allOf"] = []

            for conditional_req in conditionals_list["allOf"]:
                if conditional_req.get("if") == selector_dict:  # condition already exists
                    conditional_req["then"]["required"].append(requirement)
                    return
            conditionals_list["allOf"].append({})
            conditionals_list["allOf"][-1]["if"] = selector_dict
            conditionals_list["allOf"][-1]["then"] = {"required": [requirement]}


# -------------------------------------------------------------------------------------------------
class Enumeration:
    """Class to convert source schema Enumeration Objects into JSON"""

    def __init__(self, name, description=None):
        self._name = name
        self._enumerants = []  # list of tuple:[value, description, display_text, notes]
        self.entry = {}
        self.entry[self._name] = {}
        if description:
            self.entry[self._name]["description"] = description

    def add_enumerator(self, value, description=None, display_text=None, notes=None):
        """Store information grouped as a tuple per enumerant."""
        self._enumerants.append((value, description, display_text, notes))

    def create_dictionary_entry(self):
        """
        Convert information currently grouped per enumerant, into json groups for
        the whole enumeration.
        """
        z = list(zip(*self._enumerants))
        enums = {"type": "string", "enum": z[0]}
        if any(z[2]):
            enums["enum_text"] = z[2]
        if any(z[1]):
            enums["descriptions"] = z[1]
        if any(z[3]):
            enums["notes"] = z[3]
        self.entry[self._name] = {**self.entry[self._name], **enums}
        return self.entry


# -------------------------------------------------------------------------------------------------
class ObjectTypeList:
    """Class to organize source schema into an object-type based data structure"""

    def __init__(self, input_schema_path):
        """
        Create new data structure where keys are Object Types, and values are a list of entries
        of that type

        :param input_schema_path:   Relative or absolute path to source schema file
        """

        self._contents = load(Path(input_schema_path).absolute())
        file_object_types: set = {self._contents[base_level_tag]["Object Type"] for base_level_tag in self._contents}
        self._object_structure = {}
        for obj in file_object_types:
            self._object_structure[obj] = [
                {base_level_tag: self._contents[base_level_tag]}
                for base_level_tag in self._contents
                if self._contents[base_level_tag]["Object Type"] == obj
            ]

    @property
    def object_structure(self):
        """Return the whole reorganized structure (dict)"""
        return self._object_structure

    @property
    def file_objects(self):
        """Return a list of the object types available in the schema"""
        return self._object_structure.keys()

    def object_list(self, object_type: str):
        """
        Return the list of objects under a given key

        :param object_type: Object Type to search for, as a key
        """
        return self._object_structure.get(object_type, [])


# -------------------------------------------------------------------------------------------------
class JsonTranslator:  # pylint:disable=R0902,R0903,R0914
    """Class to translate source schema into JSON schema"""

    def __init__(self, input_file_path: Path, forward_declaration_dir: Optional[Path] = None):
        """ """
        self._schema: dict = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": None,
            "description": None,
            "definitions": {},
        }
        self._references: dict = {}
        self._fundamental_data_types: dict = {}
        source_path = input_file_path.absolute()
        self._source_dir: Path = source_path.parent
        self._forward_declaration_dir: Optional[Path] = forward_declaration_dir  # core yaml only
        self._schema_name: str = Path(source_path.stem).stem
        self._schema_object_types: set = {
            "String Type",
            "Enumeration",
        }  # "basic" object types
        self._data_group_types: set = {"Data Group"}
        self._contents: dict = load(source_path)
        sch: dict = {}

        file_objects = ObjectTypeList(input_file_path)

        # Assemble references first
        for meta_entry in file_objects.object_list("Meta"):
            for schema_section in [v for k, v in meta_entry.items()]:
                self._load_meta_info(schema_section)

        for string_type_entry in file_objects.object_list("String Type"):
            for tag, entry in string_type_entry.items():
                if "Is Regex" in entry:
                    sch.update({tag: {"type": "string", "regex": True}})
                else:
                    sch.update(
                        {
                            tag: {
                                "type": "string",
                                "pattern": entry["Regular Expression Pattern"],
                            }
                        }
                    )

        for enum_type_entry in file_objects.object_list("Enumeration"):
            for name_key in enum_type_entry.keys():
                sch.update(self._process_enumeration(name_key))

        for dgt in self._data_group_types:
            for datagroup_type_entry in file_objects.object_list(dgt):
                for tag, entry in datagroup_type_entry.items():
                    dg = DataGroup(tag, self._fundamental_data_types, self._references)
                    try:
                        sch.update(dg.add_data_group(tag, entry["Data Elements"]))
                    except RuntimeError as e:
                        # Stop execution if the resulting schema will be incomplete
                        raise RuntimeError(f"In file {source_path}: {e}") from e

        self._schema["definitions"] = sch

    @property
    def schema(self):
        """Return the translated JSON schema dictionary"""
        return self._schema

    def _load_meta_info(self, schema_section: dict):
        """Store the global/common types and the types defined by any named references."""
        self._schema["title"] = schema_section["Title"]
        self._schema["description"] = schema_section["Description"]
        if "Version" in schema_section:
            self._schema["version"] = schema_section["Version"]
        if "Root Data Group" in schema_section:
            self._schema["$ref"] = self._schema_name + ".schema.json#/definitions/" + schema_section["Root Data Group"]
        # Create a dictionary of available external objects for reference
        refs = {
            "core": load(Path(__file__).with_name("core.schema.yaml")),
            f"{self._schema_name}": load(self._source_dir / f"{self._schema_name}.schema.yaml"),
        }
        if self._schema_name == "core" and self._forward_declaration_dir and self._forward_declaration_dir.is_dir():
            for file in self._forward_declaration_dir.iterdir():
                refs.update({f"{get_base_stem(file)}": load(file)})
        elif "References" in schema_section:
            for ref in schema_section["References"]:
                try:
                    refs.update({f"{ref}": load(self._source_dir / f"{ref}.schema.yaml")})
                except RuntimeError:
                    raise RuntimeError(f"{ref} reference file does not exist.") from None
        for _, ext_dict in refs.items():
            # Append the expected object types for this schema set with any Data Group Templates
            # The 'Name' field of a Data Group Template is an object treated like
            # a Data Group subclass
            self._data_group_types.update(
                [name for name in ext_dict if ext_dict[name]["Object Type"] == "Data Group Template"]
            )
            for base_item in [name for name in ext_dict if ext_dict[name]["Object Type"] == "Data Type"]:
                self._fundamental_data_types[base_item] = ext_dict[base_item]["JSON Schema Type"]
        for ref_name, ext_dict in refs.items():
            # Populate the references map so the parser knows where to locate any object types it
            # subsequently encounters
            self._references[ref_name] = [
                base_item
                for base_item in ext_dict
                if ext_dict[base_item]["Object Type"] in self._schema_object_types | self._data_group_types
            ]

    def _process_enumeration(self, name_key: str):
        """Collect all Enumerators in an Enumeration block."""
        enums = self._contents[name_key]["Enumerators"]
        description = self._contents[name_key].get("Description")
        definition = Enumeration(name_key, description)
        for key in enums:
            try:
                descr = enums[key]["Description"] if "Description" in enums[key] else None
                displ = enums[key]["Display Text"] if "Display Text" in enums[key] else None
                notes = enums[key]["Notes"] if "Notes" in enums[key] else None
                definition.add_enumerator(key, descr, displ, notes)
            except TypeError:  # key's value is None
                definition.add_enumerator(key)
        return definition.create_dictionary_entry()


# -------------------------------------------------------------------------------------------------
def generate_core_json_schema(processing_path: Path):
    """
    Create JSON schema from core YAML schema. Any forward-declarations in core must be found in
    the schema in the processing path.

    :param processing_path:     The directory of source schema currently being processed
    """
    j = JsonTranslator(Path(__file__).with_name("core.schema.yaml"), processing_path)
    return j.schema


# -------------------------------------------------------------------------------------------------
def replace_reference(referenced_schemas: dict, subdict: dict) -> bool:
    """
    Search for $ref keys and replace the associated dictionary entry in-situ.

    :param referenced_schemas:   Keys = schema names, Values = JSON dictionary representations
    :param subdict:              Nested piece of JSON dictionary relevant to the current iteration
    """
    subbed = False
    if "$ref" in subdict.keys():
        subbed = True
        # parse the ref and locate the sub-dict (e.g. core.schema.json#/definitions/Metadata
        # parses to core.schema.json and /definitions/Metadata)
        source_file, ref_loc = subdict["$ref"].split("#")
        try:
            ref: dict = referenced_schemas[os.path.splitext(source_file)[0]]
        except KeyError as e:
            raise RuntimeError(f"{source_file} is not in list of referenced schemas.") from e
        key_tree: list = ref_loc.lstrip("/").split("/")
        try:
            sub_d = ref[key_tree[0]]
            for k in key_tree[1:]:
                sub_d = sub_d[k]
            # replace the $ref with its contents
            subdict.update(sub_d)
            subdict.pop("$ref")
            # re-search the substituted dictionary
            subbed = replace_reference(referenced_schemas, subdict)
        except KeyError:
            subbed = False  # leave schema subdictionary as-is
    else:
        for key, value in subdict.items():
            if isinstance(value, dict):
                subbed = replace_reference(referenced_schemas, value)
            if isinstance(value, list):
                for entry in [item for item in value if isinstance(item, dict)]:
                    subbed = replace_reference(referenced_schemas, entry)
    return subbed


# -------------------------------------------------------------------------------------------------
def generate_json_schema(source_schema_input_path: Path, json_schema_output_path: Path) -> None:
    """
    Create reference-resolved JSON schema from YAML source schema.

    :param source_schema_input_path:   Absolute path to source schema (YAML)
    :param json_schema_output_path:    JSON schema to write
    """
    if source_schema_input_path.is_file() and source_schema_input_path.suffixes == [".schema", ".yaml"]:
        # schema_ref_map collects all schema in the directory to use in reference
        # resolution (substituition)
        schema_ref_map = {"core.schema": generate_core_json_schema(source_schema_input_path.parent)}
        for ref_source in source_schema_input_path.parent.iterdir():
            schema_ref_map[ref_source.stem] = JsonTranslator(ref_source.absolute()).schema

        main_schema_instance = schema_ref_map[Path(source_schema_input_path).stem]
        while replace_reference(schema_ref_map, main_schema_instance):
            pass

        dump(main_schema_instance, json_schema_output_path)


# -------------------------------------------------------------------------------------------------
def get_scope_locations(
    # pylint: disable-next=dangerous-default-value # default for mutable value is intentional,
    # for recursion
    schema: dict,
    scopes_dict: dict,
    scope_key: str = "Reference",
    lineage: Optional[list] = None,
) -> None:
    """
    Populate a map of paths for a given scope name.

    :param schema:        JSON dictionary representing schema
    :param scopes_dict:   Stores all instances of the specified scope name with a path key
    :param scope_key:     Name of the scope specifier
    :param lineage:       Current location in dictionary tree
    """
    if not lineage:
        lineage = []
    for key, value in schema.items():
        if key == "scopedType" and value == scope_key:
            scopes_dict[".".join(lineage)] = schema["scope"]  # key is a dot-separated path
        elif isinstance(value, dict):
            get_scope_locations(value, scopes_dict, scope_key, lineage + [key])
        elif isinstance(value, list):
            for entry in [item for item in value if isinstance(item, dict)]:
                get_scope_locations(entry, scopes_dict, scope_key, lineage + [key])


# -------------------------------------------------------------------------------------------------
def get_reference_value(data_dict: dict, lineage: list) -> dict:
    """
    Following nested keys listed in lineage, return final value.

    :param data_dict:     JSON dictionary representing file to validate
    :param lineage:       Current location in dictionary tree
    """
    test_reference = data_dict
    for adr in lineage:
        if test_reference.get(adr):
            if isinstance(test_reference[adr], list):
                for item in test_reference[adr]:
                    return get_reference_value(item, lineage[1:])
            else:
                test_reference = test_reference[adr]
        else:
            return {}
    return test_reference


# -------------------------------------------------------------------------------------------------
def postvalidate_references(input_file: Path, input_schema: Path):
    """
    Make sure IDs and References match in scope.

    :param input_file:      JSON example to validate
    :param input_schema:    JSON schema to validate against
    :raises Exception:      When Reference scope does not match anything in ID scopes
    """
    id_scopes: dict = {}
    reference_scopes: dict = {}
    get_scope_locations(load(input_schema), scope_key="ID", scopes_dict=id_scopes)
    get_scope_locations(load(input_schema), scope_key="Reference", scopes_dict=reference_scopes)
    data = load(input_file)
    ids = []
    for id_loc in [id for id in id_scopes if id.startswith("properties")]:
        lineage = [level for level in id_loc.split(".") if level not in ["properties", "items"]]
        ids.append(get_reference_value(data, lineage))
    for ref in [r for r in reference_scopes if r.startswith("properties")]:
        lineage = [level for level in ref.split(".") if level not in ["properties", "items"]]
        reference_scope = get_reference_value(data, lineage)
        if reference_scope and reference_scope not in ids:
            raise ValueError(f"Scope mismatch in {input_file}; {reference_scope} not in ID scope list {ids}.")


# -------------------------------------------------------------------------------------------------
def validate_file(input_file: Path, input_schema: Path):
    """
    Validate example against schema.

    :param input_file:      JSON example to validate
    :param input_schema:    JSON schema to validate against
    """
    v = MetaSchema(input_schema)
    v.validate(input_file)


# -------------------------------------------------------------------------------------------------
def postvalidate_file(input_file: Path, input_schema: Path):
    """
    Validate input example against external rules; currently scopes dictated in schema.

    :param input_file:      JSON example to validate
    :param input_schema:    JSON schema to validate against
    """
    postvalidate_references(input_file, input_schema)
