import pathlib
from typing import Optional, Union

from .header_entries import *
from lattice.file_io import load, get_base_stem
from lattice.util import snake_style, hyphen_separated_lowercase_style
import lattice.cpp.support_files as support

class HeaderTranslator:
    def __init__(self):
        self._references = dict()
        self._fundamental_data_types = dict()
        self._derived_types = dict()
        self._preamble = list()
        self._doxynotes = "/// @note  This class has been auto-generated. Local changes will not be saved!\n"
        self._epilogue = list()
        self._data_group_types = ["Data Group"]
        self._forward_declaration_dir: Optional[pathlib.Path] = None
        self._required_base_classes = list()

    def __str__(self):
        s = "\n".join([p for p in self._preamble])
        s += f"\n\n{self._doxynotes}\n{self.root.value}\n"
        s += "\n".join([e for e in self._epilogue])
        return s

    @property
    def root(self):
        return self._top_namespace

    @property
    def required_base_classes(self):
        return self._required_base_classes

    @staticmethod
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

    # fmt: off
    def translate(self,
                  input_file_path: pathlib.Path,
                  forward_declarations_path: pathlib.Path,
                  output_path: pathlib.Path,
                  top_namespace: str):
        """X"""
        self._source_dir = input_file_path.parent.resolve()
        self._forward_declaration_dir = forward_declarations_path
        self._schema_name = get_base_stem(input_file_path)
        self._references.clear()
        self._derived_types.clear()
        self._fundamental_data_types.clear()
        self._preamble.clear()
        self._epilogue.clear()

        self._contents = load(input_file_path)

        # Load meta info first (assuming that base level tag == Schema means object type == Meta)
        self._load_meta_info(self._contents["Schema"])
        self._add_include_guard(snake_style(self._schema_name))
        self._add_standard_dependency_headers(self._contents["Schema"].get("References"))

        # Create "root" node(s)
        self._top_namespace = HeaderEntry(top_namespace)
        self._namespace = HeaderEntry(f"{snake_style(self._schema_name)}_ns", parent=self._top_namespace)

        # First, assemble typedefs
        for base_level_tag in [tag for tag in self._contents if self._contents[tag]["Object Type"] == "String Type"]:
            Typedef(base_level_tag, self._namespace, "std::string")

        # Second, enumerations
        for base_level_tag in self._list_objects_of_type("Enumeration"):
            Enumeration(base_level_tag, self._namespace, self._contents[base_level_tag]["Enumerators"])

        # Namespace-level dependencies
        InlineDependency("logger", self._namespace, "std::shared_ptr<Courier::Courier>")

        # Collect member objects and their children
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
        for base_level_tag in self._list_objects_of_type(self._data_group_types):
            data_group_template = self._contents[base_level_tag].get("Data Group Template", "")
            if data_group_template in data_group_plugins:
                s = data_group_plugins[data_group_template](
                    base_level_tag,
                    self._namespace,
                    superclass=data_group_template
                    )
            else:
                s = Struct(
                    base_level_tag,
                    self._namespace,
                    superclass=data_group_template,
                )
            self._add_header_dependencies(s, output_path)
            # When there is a base class, add overrides:
            self._add_function_overrides(s, output_path, data_group_template)

            # Process plugin code for the entire element group, if there is any
            if data_group_template in data_element_plugins:
                e = data_element_plugins[data_group_template](
                    s,
                    self._contents[base_level_tag]["Data Elements"]
                    )

            # Per-element processing
            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataElement(
                    data_element,
                    s,
                    self._contents[base_level_tag]["Data Elements"][data_element],
                    self._fundamental_data_types,
                    self._references,
                    self._search_nodes_for_datatype,
                )
                self._add_header_dependencies(d, output_path)
            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataIsSetElement(data_element, s)
            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataElementStaticMetainfo(
                    data_element,
                    s,
                    self._contents[base_level_tag]["Data Elements"][data_element],
                    "Units"
                )
            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataElementStaticMetainfo(
                    data_element,
                    s,
                    self._contents[base_level_tag]["Data Elements"][data_element],
                    "Description"
                )
            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataElementStaticMetainfo(
                    data_element,
                    s,
                    self._contents[base_level_tag]["Data Elements"][data_element],
                    "Name"
                )
        HeaderTranslator.modified_insertion_sort(self._namespace.child_entries)
        # PerformanceMapBase object needs sibling grid/lookup vars to be created, so parse last
        # self._add_performance_overloads()

        # Final passes through dictionary in order to add elements related to serialization
        for base_level_tag in self._list_objects_of_type("Enumeration"):
            EnumSerializationDeclaration(base_level_tag,
                                         self._namespace,
                                         self._contents[base_level_tag]["Enumerators"])
        for base_level_tag in self._list_objects_of_type(self._data_group_types):
            # from_json declarations are necessary in top container, as the header-declared
            # objects might be included and used from elsewhere.
            ObjectSerializationDeclaration(base_level_tag, self._namespace)


    def _load_meta_info(self, schema_section):
        """Store the global/common types and the types defined by any named references."""
        self._root_data_group = schema_section.get("Root Data Group")
        refs: dict = {
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
            self._data_group_types.extend(
                [name for name in ext_dict if ext_dict[name]["Object Type"] == "Data Group Template"]
            )
            self._references[ref_file] = [
                name for name in ext_dict if ext_dict[name]["Object Type"] in self._data_group_types + ["Enumeration"]
            ]
            # For every reference listed, store all the derived-class/base-class pairs as dictionaries
            self._derived_types[ref_file] = {name : ext_dict[name].get("Data Group Template") for name in ext_dict if ext_dict[name].get("Data Group Template")}

            cpp_types = {"integer": "int", "string": "std::string", "number": "double", "boolean": "bool"}
            for base_item in [name for name in ext_dict if ext_dict[name]["Object Type"] == "Data Type"]:
                self._fundamental_data_types[base_item] = cpp_types.get(ext_dict[base_item]["JSON Schema Type"])
            for base_item in [name for name in ext_dict if ext_dict[name]["Object Type"] == "String Type"]:
                self._fundamental_data_types[base_item] = "std::string"

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

    def _add_header_dependencies(self, data_element, generated_header_path: pathlib.Path):
        """Extract the dependency name from the data_element's type for included headers."""
        if "core_ns" in data_element.type:
            self._add_member_includes("core")
        if "unique_ptr" in data_element.type:
            m = re.search(r"\<(?P<base_class_type>.*)\>", data_element.type)
            if m:
                self._add_member_includes(m.group("base_class_type"), generated_header_path)
        if data_element.superclass:
            self._add_member_includes(data_element.superclass, generated_header_path)
        for external_source in data_element.external_reference_sources:
            # This piece captures any "forward-declared" types that need to be
            # processed by the DataElement type-finding mechanism before their header is known.
            self._add_member_includes(external_source)

    def _add_member_includes(self, dependency: str, generated_base_class_path: Optional[pathlib.Path] = None):
        """
        Add the dependency to the list of included headers,
        and to the list of base classes if necessary.
        """
        header_include = f"#include <{hyphen_separated_lowercase_style(dependency)}.h>"
        if header_include not in self._preamble:
            self._preamble.append(header_include)
            if generated_base_class_path:
                # self._required_base_classes.append(dependency)
                support.generate_superclass_header(dependency, generated_base_class_path)

    # fmt: off
    def _add_function_overrides(self, parent_node, output_path, base_class_name):
        """Get base class virtual functions to be overridden."""
        base_class = pathlib.Path(output_path) / f"{hyphen_separated_lowercase_style(base_class_name)}.h"
        try:
            with open(base_class) as b:
                for line in b:
                    if base_class_name not in line:
                        m = re.search(r"\s*virtual\s(?P<return_type>.*)\s(?P<name>.*)\((?P<arguments>.*)\)", line)
                        if m:
                            MemberFunctionOverride(m.group("return_type"),
                                                   m.group("name"),
                                                   f'({m.group("arguments")})',
                                                   "",
                                                   parent_node)
        except:
            pass
    # fmt: on

    def _add_performance_overloads(self, parent_node=None):
        """ """
        if not parent_node:
            parent_node = self.root
        for entry in parent_node.child_entries:
            if entry.parent and entry.superclass == "PerformanceMapBase":
                for lvstruct in [
                    lv
                    for lv in entry.parent.child_entries
                    if lv.superclass == "LookupVariablesBase"
                    and remove_prefix(lv.name, "LookupVariables") == remove_prefix(entry.name, "PerformanceMap")
                ]:
                    f_ret = f"{lvstruct.name}Struct"
                    n_ret = len([c for c in lvstruct.child_entries if isinstance(c, DataElement)])
                    # for each performance map, find GridVariables sibling of PerformanceMap, that has a matching name
                    for gridstruct in [
                        gridv
                        for gridv in entry.parent.child_entries
                        if gridv.superclass == "GridVariablesBase"
                        and remove_prefix(gridv.name, "GridVariables") == remove_prefix(entry.name, "PerformanceMap")
                    ]:
                        f_args = list()
                        for ce in [c for c in gridstruct.child_entries if isinstance(c, DataElement)]:
                            f_args.append(" ".join(["double", ce.name]))
                        f_args.append("Btwxt::Method performance_interpolation_method = Btwxt::Method::LINEAR")
                        CalculatePerformanceOverload(f_ret, f_args, "", entry, n_ret)
            else:
                self._add_performance_overloads(entry)

    def _search_references_for_base_types(self, data_element):
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

    def _list_objects_of_type(self, object_type_or_list: Union[str, list[str]]) -> list:
        if isinstance(object_type_or_list, str):
            return [tag for tag in self._contents if self._contents[tag].get("Object Type") == object_type_or_list]
        elif isinstance(object_type_or_list, list):
            return [tag for tag in self._contents if self._contents[tag].get("Object Type") in object_type_or_list]
