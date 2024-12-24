from __future__ import annotations
import pprint
import pathlib
import logging
from typing import Optional, Union

from .header_entries import *
from lattice.file_io import load, get_base_stem
from lattice.util import snake_style, hyphen_separated_lowercase_style
import lattice.cpp.support_files as support
from abc import ABC, abstractmethod

logger = logging.getLogger()


class PluginInterface(ABC):
    extensions: dict[str, Callable] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()
        if "base_class" in kwargs and isinstance(kwargs["base_class"], str):
            cls.extensions[kwargs["base_class"]] = cls

    @abstractmethod
    def process_data_group(self, parent_node: HeaderEntry): ...


def modified_insertion_sort(obj_list):
    """From https://stackabuse.com/sorting-algorithms-in-python/#insertionsort"""
    swapped = False
    # Start on the second element as we assume the first element is sorted
    for i in range(1, len(obj_list)):
        item_to_insert = obj_list[i]
        # And keep a reference of the index of the previous element
        j = i - 1
        # Move all items of the sorted segment forward if they are larger than the item to insert
        while j >= 0 and any(obj > item_to_insert for obj in obj_list[0 : j + 1]):
            obj_list[j + 1] = obj_list[j]
            swapped = True
            j -= 1
        # Insert the item
        obj_list[j + 1] = item_to_insert
    return swapped


class HeaderTranslator:
    def __init__(self):
        self._references: dict[str, list[str]] = {}
        self._fundamental_data_types: dict[str, str] = {}
        self._derived_types = {}
        self._preamble = []
        self._doxynotes = "/// @note  This class has been auto-generated. Local changes will not be saved!\n"
        self._epilogue = []
        self._data_group_types = {"Data Group"}
        self._forward_declaration_dir: Optional[pathlib.Path] = None
        self._required_base_classes = []
        self._extensions: dict[str, PluginInterface] = {
            base_class: PluginInterface.extensions[base_class]() for base_class in PluginInterface.extensions
        }

    def __str__(self):
        s = "\n".join([p for p in self._preamble])
        s += f"\n\n{self._doxynotes}\n{self.root}\n"
        s += "\n".join([e for e in self._epilogue])
        return s

    @property
    def root(self):
        return self._top_namespace

    # fmt: off
    def translate(self,
                  input_file_path: pathlib.Path,
                  forward_declarations_path: pathlib.Path,
                  output_path: pathlib.Path,
                  top_namespace: str):
        """Translate schema into C++ header file, but store locally as a data structure."""
        self._source_dir = input_file_path.parent.resolve()
        self._forward_declaration_dir = forward_declarations_path
        self._schema_name = get_base_stem(input_file_path)
        self._reset_parsing()
        self._contents = load(input_file_path)

        # Load meta info first (assuming that base level tag == Schema means object type == Meta)
        self._load_meta_info(self._contents["Schema"])
        self._add_include_guard(snake_style(self._schema_name))
        self._add_standard_dependency_headers(self._contents["Schema"].get("References"))

        self._top_namespace = HeaderEntry(top_namespace, None)
        self._namespace = HeaderEntry(f"{snake_style(self._schema_name)}_ns", self._top_namespace)

        for base_level_tag in [tag for tag in self._contents if self._contents[tag]["Object Type"] == "String Type"]:
            Typedef(base_level_tag, self._namespace, "std::string")

        for base_level_tag in self._list_objects_of_type("Enumeration"):
            Enumeration(base_level_tag, self._namespace, self._contents[base_level_tag]["Enumerators"])

        InlineDependency("logger", self._namespace, "std::shared_ptr<Courier::Courier>")

        # Collect member objects and their children, building the header element tree
        for base_level_tag in self._list_objects_of_type("Meta"):
            s = Struct(base_level_tag, self._namespace)
            d = DataElementStaticMetainfo(base_level_tag.lower(),
                                          s,
                                          self._contents[base_level_tag],
                                          "Title")
            d = DataElementStaticMetainfo(base_level_tag.lower(),
                                          s,
                                          self._contents[base_level_tag],
                                          "Version")
            d = DataElementStaticMetainfo(base_level_tag.lower(),
                                          s,
                                          self._contents[base_level_tag],
                                          "Description")

        for base_level_tag in self._list_objects_of_type("Data Group Template"):
            # TODO: If header does not already exist as a separate file, then
            class_entry = Struct(base_level_tag, self._namespace)
            dtor = VirtualDestructor("", class_entry, "", base_level_tag, [])
            # TODO: else, copy contents into tree?

        for base_level_tag in self._list_objects_of_type(self._data_group_types):
            data_group_template = self._contents[base_level_tag].get("Data Group Template", "")
            s = Struct(
                base_level_tag,
                self._namespace,
                superclass=data_group_template,
            )
            self._process_data_elements(s, base_level_tag, data_group_template)
            self._add_function_overrides(s, output_path, data_group_template)

        # Process customizations
        for base_level_tag in self._list_objects_of_type(self._data_group_types):
            data_group_template = self._contents[base_level_tag].get("Data Group Template", "")
            if data_group_template in self._extensions:
                self._extensions[data_group_template].process_data_group(self.root)
                self._extensions.pop(data_group_template)

        self._add_header_dependencies(output_path)
        modified_insertion_sort(self._namespace.child_entries)

        # Final passes through dictionary in order to add elements related to serialization
        for base_level_tag in self._list_objects_of_type("Enumeration"):
            EnumSerializationDeclaration(base_level_tag,
                                         self._namespace,
                                         self._contents[base_level_tag]["Enumerators"])
        for base_level_tag in self._list_objects_of_type(self._data_group_types):
            # from_json declarations are necessary in top container, as the header-declared
            # objects might be included and used from elsewhere.
            ObjectSerializationDeclaration(base_level_tag, self._namespace)

    def _reset_parsing(self):
        """Clear member containers for a new translation."""
        self._references.clear()
        self._derived_types.clear()
        self._fundamental_data_types.clear()
        self._preamble.clear()
        self._epilogue.clear()

    def _load_meta_info(self, schema_section):
        """Store the global/common types and the types defined by any named references."""
        self._root_data_group = schema_section.get("Root Data Group")
        refs: dict[str, pathlib.Path] = {
            f"{self._schema_name}": self._source_dir / f"{self._schema_name}.schema.yaml",
            "core": pathlib.Path(__file__).parent.with_name("core.schema.yaml"),
        }
        if "References" in schema_section:
            for ref in schema_section["References"]:
                refs.update({f"{ref}": self._source_dir / f"{ref}.schema.yaml"})
        if (self._schema_name == "core" and
            self._forward_declaration_dir and
            self._forward_declaration_dir.is_dir()):
            for file in self._forward_declaration_dir.iterdir():
                ref = get_base_stem(file)
                refs.update({ref: file})

        for ref_file in refs:
            ext_dict = load(refs[ref_file])
            # Load every explicitly listed reference and collect the base classes therein
            self._data_group_types.update(
                [name for name in ext_dict if ext_dict[name]["Object Type"] == "Data Group Template"]
            )
            self._references[ref_file] = [
                name for name in ext_dict if ext_dict[name]["Object Type"] in list(self._data_group_types) + ["Enumeration"]
            ]
            # For every reference listed, store all the derived-class/base-class pairs as dictionaries
            self._derived_types[ref_file] = {name : ext_dict[name].get("Data Group Template") for name in ext_dict if ext_dict[name].get("Data Group Template")}

            cpp_types = {"integer": "int",
                         "string": "std::string",
                         "number": "double",
                         "boolean": "bool"}
            for base_item in [name for name in ext_dict if ext_dict[name]["Object Type"] == "Data Type"]:
                self._fundamental_data_types[base_item] = cpp_types[ext_dict[base_item]["JSON Schema Type"]]
            for base_item in [name for name in ext_dict if ext_dict[name]["Object Type"] == "String Type"]:
                self._fundamental_data_types[base_item] = "std::string"

        print(self._schema_name, "References")
        pprint.pp(self._references)
        print(self._schema_name, "Derived types")
        pprint.pp(self._derived_types)

    # fmt: on

    def _add_include_guard(self, header_name):
        """Populate the file's include guards."""
        s1 = f"#ifndef {header_name.upper()}_H_"
        s2 = f"#define {header_name.upper()}_H_"
        s3 = f"#endif"
        self._preamble.extend([s1, s2])
        self._epilogue.append(s3)

    def _add_standard_dependency_headers(self, ref_list):
        """Populate a list of #includes that every lattice-based project will need."""
        if ref_list:
            includes = ""
            for r in ref_list:
                include = f"#include <{hyphen_separated_lowercase_style(r)}.h>"
                self._preamble.append(include)
        self._preamble.extend(
            [
                "#include <string>",
                "#include <vector>",
                "#include <nlohmann/json.hpp>",
                "#include <enum-info.h>",
                "#include <courier/courier.h>",
            ]
        )

    def _add_header_dependencies(self, generated_header_path: pathlib.Path, parent_node=None):  # header_element, ):
        """Extract the dependency name from the data_element's type for included headers."""
        if not parent_node:
            parent_node = self.root
        for entry in parent_node.child_entries:
            if isinstance(entry, DataElement):
                if "core_ns" in entry.type:
                    self._add_member_includes("core")
                if "unique_ptr" in entry.type:
                    m = re.search(r"\<(?P<base_class_type>.*)\>", entry.type)
                    if m:
                        self._add_member_includes(m.group("base_class_type"), generated_header_path)
                if entry.scoped_innertype[0] and entry.scoped_innertype[0].lower() != self._schema_name.lower():
                    # This piece captures any "forward-declared" types that need to be
                    # processed by the DataElement type-finding mechanism before their header is known.
                    # Don't include one's self
                    self._add_member_includes(entry.scoped_innertype[0])
            elif isinstance(entry, Struct):
                if entry.superclass:
                    #TODO: Now we have to look for the class in the header tree instead of assuming it's in its own file
                    self._add_member_includes(entry.superclass, generated_header_path)
                self._add_header_dependencies(generated_header_path, entry)

            else:
                self._add_header_dependencies(generated_header_path, entry)

    def _add_member_includes(self, dependency: str, generated_base_class_path: Optional[pathlib.Path] = None):
        """
        Add the dependency to the list of included headers, and generate the header file if it's a base class.
        """
        header_include = f"#include <{hyphen_separated_lowercase_style(dependency)}.h>"
        if header_include not in self._preamble:
            self._preamble.append(header_include)
            # if generated_base_class_path:
            #     support.generate_superclass_header(dependency, generated_base_class_path)

    def _process_data_elements(self, data_group_entry: HeaderEntry, base_level_tag: str, data_group_template: str):
        """Iterate over child Data Elements and assign them to a parent struct."""

        # Per-element processing
        for data_element in self._contents[base_level_tag]["Data Elements"]:
            d = DataElement(
                data_element,
                data_group_entry,
                self._contents[base_level_tag]["Data Elements"][data_element],
                self._fundamental_data_types,
                self._references,
                self._search_nodes_for_datatype,
            )
            d_is_set = DataElementIsSetFlag(data_element, data_group_entry)
            d_units = DataElementStaticMetainfo(
                data_element, data_group_entry, self._contents[base_level_tag]["Data Elements"][data_element], "Units"
            )
            d_desc = DataElementStaticMetainfo(
                data_element,
                data_group_entry,
                self._contents[base_level_tag]["Data Elements"][data_element],
                "Description",
            )
            d_name = DataElementStaticMetainfo(
                data_element, data_group_entry, self._contents[base_level_tag]["Data Elements"][data_element], "Name"
            )

    # fmt: off
    def _add_function_overrides(self, parent_node, output_path, base_class_name):
        """Get base class virtual functions to be overridden."""
        # TODO: Not looking in a base class file anymore
        base_class = pathlib.Path(output_path) / f"{hyphen_separated_lowercase_style(base_class_name)}.h"
        try:
            with open(base_class) as b:
                for line in b:
                    if base_class_name not in line: # avoid overriding a virtual destructor
                        m = re.search(r"\s*virtual\s(?P<return_type>.*)\s(?P<name>.*)\((?P<arguments>.*)\)", line)
                        if m:
                            MemberFunctionOverrideDeclaration("",
                                                              parent_node,
                                                              m.group("return_type"),
                                                              m.group("name"),
                                                              m.group("arguments").split(","))
        except:
            pass
    # fmt: on

    def _search_references_for_base_types(self, data_element) -> str | None:
        """
        Search the pre-populated derived-class list for base class type. Used
        when a Data Type requested in a selector constraint is defined in a schema's references rather than in-file.
        """
        data_element_unscoped = data_element.split(":")[-1]
        for reference in self._derived_types:
            if self._derived_types[reference].get(data_element_unscoped) in self._data_group_types:
                return self._derived_types[reference][data_element_unscoped]
        return None

    def _search_nodes_for_datatype(self, data_element) -> str:
        """
        If data_element exists, return its data type; else return the data group's 'data type,' which
        is the Data Group Template (base class type). Hacky overload.
        """
        base_class_type = self._search_references_for_base_types(data_element)
        if base_class_type:
            return base_class_type
        else:
            for listing in self._contents:
                if "Data Elements" in self._contents[listing]:
                    # if "Data Group Template" in self._contents[listing] and listing in data_element:
                    #     return self._contents[listing]["Data Group Template"]

                    for element in self._contents[listing]["Data Elements"]:
                        if element == data_element and "Data Type" in self._contents[listing]["Data Elements"][element]:
                            return self._contents[listing]["Data Elements"][element]["Data Type"]
        return "MissingType"  # Placeholder base class

    def _list_objects_of_type(self, object_type_or_list: Union[str, list[str], set[str]]) -> list:
        if isinstance(object_type_or_list, str):
            return [tag for tag in self._contents if self._contents[tag].get("Object Type") == object_type_or_list]
        elif isinstance(object_type_or_list, list) or isinstance(object_type_or_list, set):
            return [tag for tag in self._contents if self._contents[tag].get("Object Type") in object_type_or_list]
        else:
            return []
