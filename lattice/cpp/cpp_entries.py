from __future__ import (
    annotations,
)  # Allows us to annotate types that are not yet fully defined; i.e. ImplementationEntry
import logging
from typing import Optional, Callable
from dataclasses import dataclass, field

from .header_entries import (
    EntryFormat,
    HeaderEntry,
    Struct,
    DataElement,
    DataElementStaticMetainfo,
    FunctionalHeaderEntry,
    MemberFunctionOverrideDeclaration,
    ObjectSerializationDeclaration,
    InlineDependency,
)
from lattice.util import snake_style

logger = logging.getLogger()


def remove_prefix(text, prefix):
    return text[len(prefix) :] if text.startswith(prefix) else text


data_group_extensions: dict[str, Callable] = {}


def register_data_group_implementation(data_group_template_name: str, header_entry: Callable):
    data_group_extensions[data_group_template_name] = header_entry


data_element_extensions: dict[str, Callable] = {}


def register_data_element_implementation(data_group_template_name: str, header_entry: Callable):
    data_element_extensions[data_group_template_name] = header_entry


@dataclass
class ImplementationEntry(EntryFormat):
    _header_entry: HeaderEntry
    _parent: Optional[ImplementationEntry]
    _child_entries: list[ImplementationEntry] = field(init=False, default_factory=list)
    _func: str = field(init=False)

    def __post_init__(self):
        self._name = self._header_entry.name
        self._type = self._header_entry.type
        self._access_specifier: str = ""

        if self._parent:
            self._parent._add_child_entry(self)
        self._level = self._get_level()
        self._indent = self._level * "\t"

    def _add_child_entry(self, child: ImplementationEntry) -> None:
        self._child_entries.append(child)

    def _get_level(self, level: int = 0) -> int:
        if self._parent:
            return self._parent._get_level(level + 1)
        else:
            return level

    @property
    def level(self):
        return self._get_level()

    def __str__(self):
        entry = self._indent + self._type + " " + self._name + " " + " " + self._opener + "\n"
        entry += self._indent + self._access_specifier + "\n"
        entry += "\n".join([str(c) for c in self._child_entries]) + "\n"
        entry += self._indent + self._closure

        return entry


@dataclass
class DataElementStaticInitialization(ImplementationEntry):
    _header_entry: DataElementStaticMetainfo

    def __post_init__(self):
        super().__post_init__()
        type_spec = self._header_entry._type_specifier.replace("static", "").strip(" ")
        assert self._header_entry.parent is not None
        self._func = " ".join(
            [
                type_spec,
                self._type,
                f"{self._header_entry.parent.name}::{self._name}",
                "=",
                f'"{self._header_entry.init_val}";',
            ]
        )
        self.trace()

    def __str__(self):
        entry = self._indent + self._func + "\n"
        return entry


@dataclass
class DependencyInitialization(ImplementationEntry):
    _header_entry: InlineDependency

    def __post_init__(self):
        super().__post_init__()
        self._func = f"void set_{self._name} ({self._type} value) {{ {self._name} = value; }}"
        self.trace()

    def __str__(self):
        entry = self._indent + self._func + "\n"
        return entry


@dataclass
class FunctionDefinition(ImplementationEntry):
    _header_entry: FunctionalHeaderEntry

    def __post_init__(self):
        super().__post_init__()
        self._func = f"void {self._header_entry._f_name}{self._header_entry.args}"

    def __str__(self):
        entry = self._indent + self._func + " " + self._opener + "\n"
        entry += "".join([str(c) for c in self._child_entries])
        entry += self._indent + self._closure
        return entry


@dataclass
class FreeFunctionDefinition(FunctionDefinition):
    _header_entry: ObjectSerializationDeclaration


@dataclass
class StructSerialization(FunctionDefinition):
    _header_entry: Struct

    def __post_init__(self):
        super(FunctionDefinition, self).__post_init__()
        self._func = f"void from_json(const nlohmann::json& j, {self._name}& x)"

        self.trace()


@dataclass
class MemberFunctionDefinition(FunctionDefinition):
    _header_entry: MemberFunctionOverrideDeclaration

    def __post_init__(self):
        super(FunctionDefinition, self).__post_init__()
        # args = self.header_entry.args
        args = "(" + ", ".join([a.split("=")[0] for a in self._header_entry._f_args]) + ")"
        assert self._header_entry.parent is not None
        self._func = f"{self._header_entry._f_ret} {self._header_entry.parent.name}::{self._header_entry._f_name}{args}"
        self.trace()


@dataclass
class ElementSerialization(ImplementationEntry):
    _header_entry: DataElement

    def __post_init__(self):
        super().__post_init__()
        self._funclines = [
            f'json_get<{self._type}>(j, logger.get(), "{self._name}", {self._name}, {self._name}_is_set, {"true" if self._header_entry.is_required else "false"});'
        ]
        self.trace()

    def __str__(self):
        return "\n".join([(self._indent + f) for f in self._funclines]) + "\n"


@dataclass
class OwnedElementSerialization(ElementSerialization):
    def __post_init__(self):
        super().__post_init__()
        self._funclines = [
            f'json_get<{self._type}>(j, logger.get(), "{self._name}", x.{self._name}, x.{self._name}_is_set, {"true" if self._header_entry.is_required else "false"});'
        ]
        self.trace()


@dataclass
class OwnedElementCreation(ElementSerialization):
    def __post_init__(self):
        super().__post_init__()
        self._funclines = []
        assert len(self._header_entry.selector) == 1  # only one switchable data element per entry
        data_element = next(iter(self._header_entry.selector))
        for enum in self._header_entry.selector[data_element]:
            self._funclines += [
                f"if (x.{data_element} == {enum}) {{",
                f"\tx.{self._name} = std::make_unique<{self._header_entry.selector[data_element][enum]}>();",
                f"\tif (x.{self._name}) {{",
                f'\t\tfrom_json(j.at("{self._name}"), *dynamic_cast<{self._header_entry.selector[data_element][enum]}*>(x.{self._name}.get()));',
                "\t}",
                "}",
            ]
        self.trace()


@dataclass
class ClassFactoryCreation(ElementSerialization):
    def __post_init__(self):
        super().__post_init__()
        assert len(self._header_entry.selector) == 1  # only one switchable data element per entry
        data_element = next(iter(self._header_entry.selector))
        for enum in self._header_entry.selector[data_element]:
            self._funclines += [
                f"if ({data_element} == {enum}) {{",
                f'\t{self._name} = {self._name}Factory::create("{self._header_entry.selector[data_element][enum]}");',
                f"\tif ({self._name}) {{",
                f'\t\t{self._name}->initialize(j.at("{self._name}"));',
                "\t}",
                "}",
            ]
        self.trace()


@dataclass
class SerializeFromInitFunction(ElementSerialization):
    def __post_init__(self):
        super().__post_init__()
        self._func = "x.initialize(j);\n"
        self.trace()

    def __str__(self):
        return self._indent + self._func


# # -------------------------------------------------------------------------------------------------
# class PerformanceMapImplementation(ElementSerialization):
#     def __init__(self, parent, header_entry, populates_self=False):
#         super().__init__(parent, header_entry)
#         if populates_self:
#             self._func = f"{self._name}.populate_performance_map(this);\n"
#         else:
#             self._func = f"x.{self._name}.populate_performance_map(&x);\n"

#     @property
#     def value(self):
#         return self.level * "\t" + self._func


# # -------------------------------------------------------------------------------------------------
# class GridAxisImplementation(ImplementationEntry):
#     def __init__(self, name, parent):
#         super().__init__(name, parent)
#         self._func = [f"add_grid_axis(performance_map, {name});\n"]

#     @property
#     def value(self):
#         entry = ""
#         for f in self._func:
#             entry += self.level * "\t" + f
#         return entry


# # -------------------------------------------------------------------------------------------------
# class GridAxisFinalize(ImplementationEntry):
#     def __init__(self, name, parent):
#         super().__init__(name, parent)
#         self._func = [f"performance_map->finalize_grid();\n"]

#     @property
#     def value(self):
#         entry = ""
#         for f in self._func:
#             entry += self.level * "\t" + f
#         return entry


# # -------------------------------------------------------------------------------------------------
# class DataTableImplementation(ImplementationEntry):
#     def __init__(self, name, parent):
#         super().__init__(name, parent)
#         self._func = [f"add_data_table(performance_map, {name});\n"]

#     @property
#     def value(self):
#         entry = ""
#         for f in self._func:
#             entry += self.level * "\t" + f
#         return entry


# # -------------------------------------------------------------------------------------------------
# class PerformanceOverloadImplementation(ElementSerialization):
#     def __init__(self, header_entry, parent):
#         super().__init__(None, None, parent, None)
#         self._func = []
#         args = ", ".join([f"{a[1]}" for a in [arg.split(" ") for arg in header_entry.args_as_list[:-1]]])
#         self._func.append(f"std::vector<double> target {{{args}}};")
#         self._func.append(
#             "auto v = PerformanceMapBase::calculate_performance(target, performance_interpolation_method);"
#         )
#         init_str = f"{header_entry.ret_type} s {{"
#         for i in range(header_entry.n_return_values):
#             init_str += f"v[{i}], "
#         init_str += "};"
#         self._func.append(init_str)
#         self._func.append("return s;")


# -------------------------------------------------------------------------------------------------
class SimpleReturnProperty(ImplementationEntry):

    def __str__(self):
        self._func = f'return "{self._name}";'
        entry = self._indent + f'return "{self._name}";' + "\n"
        return entry


# -------------------------------------------------------------------------------------------------
class CPPTranslator:
    def __init__(self):
        self._preamble = list()

    def __str__(self):
        s = "".join(self._preamble)
        s += "\n"
        s += str(self._top_namespace)
        s += "\n"
        return s

    def translate(self, container_class_name, header_tree):
        """X"""
        self._add_included_headers(header_tree._schema_name)

        # Create "root" node(s)
        self._top_namespace = ImplementationEntry(header_tree.root, None)
        self._namespace = ImplementationEntry(
            header_tree._namespace, self._top_namespace
        )  # TODO: HeaderEntry._namespace isn't really supposed to be public

        self._get_items_to_serialize(header_tree.root)

    def _get_items_to_serialize(self, header_tree):
        for entry in header_tree.child_entries:
            if isinstance(entry, Struct) and len([c for c in entry.child_entries if isinstance(c, DataElement)]):
                # Create the "from_json" function definition (header), only if it won't be empty
                s = StructSerialization(entry, self._namespace)
                for data_element_entry in [c for c in entry.child_entries if isinstance(c, DataElement)]:
                    # In function body, create each "get_to" for individual data elements
                    if "unique_ptr" in data_element_entry.type:
                        OwnedElementCreation(data_element_entry, s)
                    else:
                        OwnedElementSerialization(data_element_entry, s)
                    # In the special case of a performance_map subclass, add calls to its
                    # members' Populate_performance_map functions
                    # if entry.superclass == "PerformanceMapBase":
                    #     PerformanceMapImplementation(data_element_entry.name, s)

            elif isinstance(entry, DataElementStaticMetainfo):
                DataElementStaticInitialization(entry, self._namespace)

            elif isinstance(entry, InlineDependency):
                DependencyInitialization(entry, self._namespace)

            # Initialize and Populate overrides (Currently the only Member_function_override is the Initialize override)
            elif isinstance(entry, MemberFunctionOverrideDeclaration):
                # Create the override function definition (header) using the declaration's signature
                m = MemberFunctionDefinition(entry, self._namespace)
                # In function body, choose element-wise ops based on the superclass
                for data_element_entry in [c for c in entry.parent.child_entries if isinstance(c, DataElement)]:
                    if "unique_ptr" in data_element_entry.type:
                        ClassFactoryCreation(data_element_entry, m)
                        self._preamble.append(f"#include <{data_element_entry.name}_factory.h>\n")
                    # else:
                    #     if entry.parent.superclass == "GridVariablesBase":
                    #         GridAxisImplementation(data_element_entry.name, m)
                    #     elif entry.parent.superclass == "LookupVariablesBase":
                    #         DataTableImplementation(data_element_entry.name, m)
                    #     elif entry.parent.superclass == "PerformanceMapBase":
                    #         ElementSerialization(
                    #             data_element_entry.name, data_element_entry.type, m, data_element_entry._is_required
                    #         )
                    #     else:
                    #         ElementSerialization(
                    #             data_element_entry.name, data_element_entry.type, m, data_element_entry._is_required
                    #         )
                    #     if entry.parent.superclass == "PerformanceMapBase":
                    #         PerformanceMapImplementation(data_element_entry.name, m, populates_self=True)
                # # Special case of grid_axis_base needs a finalize function after all grid axes
                # # are added
                # if entry.parent.superclass == "GridVariablesBase":
                #     GridAxisFinalize("", m)
            # '''
            # if data_group_template in data_group_extensions:
            #     s = data_group_extensions[data_group_template](
            #         entry,
            #         self._namespace
            #         )
            # '''
            # if isinstance(entry, CalculatePerformanceOverload):
            #     m = MemberFunctionDefinition(entry, self._namespace)
            #     for data_element_entry in [c for c in entry.parent.child_entries if isinstance(c, DataElement)]:
            #         # Build internals of Calculate_performance function
            #         if data_element_entry.name == "grid_variables":
            #             PerformanceOverloadImplementation(entry, m)

            # Lastly, handle the special case of objects that need both serialization
            # and initialization (currently a bit of a hack specific to this project)

            # elif isinstance(entry, ObjectSerializationDeclaration) and entry.name in self._namespace._name:
            #     s = FreeFunctionDefinition(entry, self._namespace)
            #     SerializeFromInitFunction(entry, s)
            self._get_items_to_serialize(entry)

    def _add_included_headers(self, main_header):
        self._preamble.clear()
        self._preamble.append(f"#include <{snake_style(main_header)}.h>\n#include <load-object.h>\n")
