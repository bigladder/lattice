from __future__ import (
    annotations,
)  # Allows us to annotate types that are not yet fully defined; i.e. ImplementationEntry

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

from .header_entries import (
    DataElement,
    DataElementStaticMetainfo,
    EntryFormat,
    FunctionalHeaderEntry,
    HeaderEntry,
    InlineDependency,
    ObjectSerializationDeclaration,
    Struct,
    VirtualDestructor,
)

logger = logging.getLogger()

# ruff: noqa: F841

def remove_prefix(text, prefix):
    return text[len(prefix) :] if text.startswith(prefix) else text


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
    _header_entry: FunctionalHeaderEntry

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
            f'json_get<{self._type}>(j, logger.get(), "{self._name}", {self._name}, {self._name}_is_set, {"true" if self._header_entry.is_required else "false"});' # noqa: E501
        ]
        self.trace()

    def __str__(self):
        return "\n".join([(self._indent + f) for f in self._funclines]) + "\n"


@dataclass
class OwnedElementSerialization(ElementSerialization):
    def __post_init__(self):
        super().__post_init__()
        self._funclines = [
            f'json_get<{self._type}>(j, logger.get(), "{self._name}", x.{self._name}, x.{self._name}_is_set, {"true" if self._header_entry.is_required else "false"});' # noqa: E501
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
                f'\t\tfrom_json(j.at("{self._name}"), *dynamic_cast<{self._header_entry.selector[data_element][enum]}*>(x.{self._name}.get()));', # noqa: E501
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


# @dataclass
# class SerializeFromInitFunction(ElementSerialization):
#     _header_entry: ObjectSerializationDeclaration

#     def __post_init__(self):
#         super().__post_init__()
#         self._func = "x.initialize(j);\n"
#         self.trace()

#     def __str__(self):
#         return self._indent + self._func


# class SimpleReturnProperty(ImplementationEntry):

#     def __str__(self):
#         self._func = f'return "{self._name}";'
#         entry = self._indent + f'return "{self._name}";' + "\n"
#         return entry


class CPPExtensionInterface(ABC):
    extensions: list[Callable] = []

    def __init_subclass__(cls):
        super().__init_subclass__()
        cls.extensions.append(cls)

    @abstractmethod
    def process_data_group(self, reference_header_entry: HeaderEntry, parent_node: ImplementationEntry): ...


class CPPTranslator:
    def __init__(self, container_class_name, header_tree):
        self._preamble = list()
        self._extensions = [extension_object() for extension_object in CPPExtensionInterface.extensions]
        self._translate(container_class_name, header_tree)

    def __str__(self):
        s = "".join(self._preamble)
        s += "\n"
        s += str(self._top_namespace)
        s += "\n"
        return s

    def _translate(self, container_class_name, header_tree):
        """X"""
        self._add_included_headers(header_tree._schema_name)

        # Create "root" node(s)
        self._top_namespace = ImplementationEntry(header_tree.root, None)
        self._namespace = ImplementationEntry(
            header_tree._namespace, self._top_namespace
        )  # TODO: HeaderEntry._namespace isn't really supposed to be public

        self._get_items_to_serialize(header_tree.root)

    def _get_items_to_serialize(self, header_tree: HeaderEntry):
        for h_entry in header_tree.child_entries:
            cpp_entry: Optional[ImplementationEntry] = None
            logger.debug(f"Header entry being processed: {h_entry.name} under {h_entry.parent.name}")
            if isinstance(h_entry, Struct) and len([c for c in h_entry.child_entries if isinstance(c, DataElement)]):
                cpp_entry = StructSerialization(
                    h_entry, self._namespace
                )  # Create the "from_json" function definition (header), only if it won't be empty

                for data_element_entry in [c for c in h_entry.child_entries if isinstance(c, DataElement)]:
                    # In function body, create each "get_to" for individual data elements
                    if "unique_ptr" in data_element_entry.type:
                        c = OwnedElementCreation(data_element_entry, cpp_entry)
                    else:
                        c = OwnedElementSerialization(data_element_entry, cpp_entry)

            elif isinstance(h_entry, DataElementStaticMetainfo):
                logger.debug(f"{h_entry.name} under {type(h_entry.parent)} under {self._namespace._name}")
                cpp_entry = DataElementStaticInitialization(h_entry, self._namespace)

            elif isinstance(h_entry, InlineDependency):
                cpp_entry = DependencyInitialization(h_entry, self._namespace)

            # Initialize and Populate overrides (Currently the only Member_function_override is the Initialize override)
            elif (
                isinstance(h_entry, FunctionalHeaderEntry)
                and not isinstance(h_entry, ObjectSerializationDeclaration)
                and not isinstance(h_entry, VirtualDestructor)
            ):
                cpp_entry = MemberFunctionDefinition(
                    h_entry, self._namespace
                )  # Create the override function definition (header) using the declaration's signature

                # In function body, choose element-wise ops based on the superclass
                for data_element_entry in [c for c in h_entry.parent.child_entries if isinstance(c, DataElement)]:
                    if "unique_ptr" in data_element_entry.type:
                        ClassFactoryCreation(data_element_entry, cpp_entry)
                        self._preamble.append(f"#include <{data_element_entry.name}_factory.h>\n")

            # Process customizations
            for plugin in self._extensions:
                if cpp_entry:
                    plugin.process_data_group(h_entry, cpp_entry)

            self._get_items_to_serialize(h_entry)

    def _add_included_headers(self, main_header):
        self._preamble.clear()
        self._preamble.append(f"#include <{main_header}.h>\n#include <load-object.h>\n")
