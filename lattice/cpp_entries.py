from .header_entries import (
    HeaderEntry,
    Struct,
    DataElement,
    DataIsSetElement,
    DataElementStaticMetainfo,
    MemberFunctionOverride,
    ObjectSerializationDeclaration,
    InlineDependency
)
from .util import snake_style
from collections import defaultdict


# -------------------------------------------------------------------------------------------------
class ImplementationEntry:
    def __init__(self, name, parent=None):
        self._type = "namespace"
        self._scope = ""
        self._name = name
        self._opener = "{"
        self._access_specifier = ""
        self._closure = "}"
        self._parent_entry = parent
        self._child_entries = list()  # of Implementation_entry(s)
        self._value = None

        if parent:
            self._lineage = parent._lineage + [name]
            self._parent_entry._add_child_entry(self)
        else:
            self._lineage = [name]

    def _add_child_entry(self, child):
        self._child_entries.append(child)

    def _get_level(self, level=0):
        if self._parent_entry:
            return self._parent_entry._get_level(level + 1)
        else:
            return level

    @property
    def level(self):
        return self._get_level()

    @property
    def value(self):
        entry = self.level * "\t" + self._type + " " + self._name + " " + " " + self._opener + "\n"
        entry += (self.level) * "\t" + self._access_specifier + "\n"
        for c in self._child_entries:
            entry += c.value + "\n"
        entry += self.level * "\t" + self._closure
        return entry


# -------------------------------------------------------------------------------------------------
class DataElementStaticInitialization(ImplementationEntry):
    def __init__(self, header_entry: DataElementStaticMetainfo, parent: ImplementationEntry = None):
        super().__init__(None, parent)
        type_spec = header_entry._type_specifier.replace("static", "").strip(" ")
        self._func = f'{type_spec} {header_entry.type} {header_entry.parent.name}::{header_entry.name} = "{header_entry.init_val}";'
        self._func = " ".join(
            [
                type_spec,
                header_entry.type,
                f"{header_entry.parent.name}::{header_entry.name}",
                "=",
                f'"{header_entry.init_val}";',
            ]
        )

    @property
    def value(self):
        entry = self.level * "\t" + self._func + "\n"
        return entry


# -------------------------------------------------------------------------------------------------
class DependencyInitialization(ImplementationEntry):
    def __init__(self, header_entry: InlineDependency, parent: ImplementationEntry = None):
        super().__init__(None, parent)
        self._func = f'void set_{header_entry.name} ({header_entry.type} value) {{ {header_entry.name} = std::move(value); }}'

    @property
    def value(self):
        entry = self.level * "\t" + self._func + "\n"
        return entry


# -------------------------------------------------------------------------------------------------
class FreeFunctionDefinition(ImplementationEntry):
    def __init__(self, header_entry, parent=None):
        super().__init__(None, parent)
        self._func = f"void {header_entry.fname}{header_entry.args}"

    @property
    def value(self):
        entry = self.level * "\t" + self._func + " " + self._opener + "\n"
        for c in self._child_entries:
            entry += c.value
        entry += self.level * "\t" + self._closure
        return entry


# -------------------------------------------------------------------------------------------------
class MemberFunctionDefinition(ImplementationEntry):
    def __init__(self, header_entry: MemberFunctionOverride, parent: ImplementationEntry = None):
        super().__init__(None, parent)
        args = header_entry.args
        if hasattr(header_entry, "args_as_list"):
            args = "(" + ", ".join([a.split("=")[0] for a in header_entry.args_as_list]) + ")"
        self._func = f"{header_entry.ret_type} {header_entry.parent.name}::{header_entry.fname}{args}"

    @property
    def value(self):
        entry = self.level * "\t" + self._func + " " + self._opener + "\n"
        for c in self._child_entries:
            entry += c.value
        entry += self.level * "\t" + self._closure
        return entry


# -------------------------------------------------------------------------------------------------
class StructSerialization(ImplementationEntry):
    def __init__(self, name, parent=None):
        super().__init__(name, parent)
        self._func = f"void from_json(const nlohmann::json& j, {name}& x)"

    @property
    def value(self):
        entry = self.level * "\t" + self._func + " " + self._opener + "\n"
        for c in self._child_entries:
            entry += c.value
        entry += self.level * "\t" + self._closure
        return entry


# -------------------------------------------------------------------------------------------------
class ElementSerialization(ImplementationEntry):
    def __init__(self, parent, header_entry: DataElement):
        super().__init__(header_entry.name, parent)
        self._func = [
            f'json_get<{header_entry.type}>(j, logger.get(), "{self._name}", {self._name}, {self._name}_is_set, {"true" if header_entry.is_required else "false"});'
        ]

    @property
    def value(self):
        entry = ""
        for f in self._func:
            entry += self.level * "\t" + f + "\n"
        return entry


# -------------------------------------------------------------------------------------------------
class OwnedElementSerialization(ElementSerialization):
    def __init__(self, parent, header_entry: DataElement):
        super().__init__(parent, header_entry)
        self._func = [
            f'json_get<{header_entry.type}>(j, logger.get(), "{self._name}", x.{self._name}, x.{self._name}_is_set, {"true" if header_entry.is_required else "false"});'
        ]


# -------------------------------------------------------------------------------------------------
class OwnedElementCreation(ElementSerialization):
    def __init__(self, parent, header_entry: DataElement):
        super().__init__(parent, header_entry)
        self._func = []
        assert len(header_entry.selector) == 1  # only one switchable data element per entry
        data_element = next(iter(header_entry.selector))
        for enum in header_entry.selector[data_element]:
            self._func += [
                f"if (x.{data_element} == {enum}) {{",
                f"\tx.{self._name} = std::make_unique<{header_entry.selector[data_element][enum]}>();",
                f"\tif (x.{self._name}) {{",
                f'\t\tx.{self._name}->initialize(j.at("{self._name}"));',
                "\t}",
                "}",
            ]


# -------------------------------------------------------------------------------------------------
class ClassFactoryCreation(ElementSerialization):
    def __init__(self, parent, header_entry: DataElement):
        super().__init__(parent, header_entry)
        assert len(header_entry.selector) == 1  # only one switchable data element per entry
        data_element = next(iter(header_entry.selector))
        for enum in header_entry.selector[data_element]:
            self._func += [
                f"if ({data_element} == {enum}) {{",
                f'\t{self._name} = {self._name}Factory::create("{header_entry.selector[data_element][enum]}");',
                f"\tif ({self._name}) {{",
                f'\t\t{self._name}->initialize(j.at("{self._name}"));',
                "\t}",
                "}",
            ]


# -------------------------------------------------------------------------------------------------
class SerializeFromInitFunction(ElementSerialization):
    def __init__(self, parent, header_entry):
        super().__init__(parent, header_entry)
        self._func = "x.initialize(j);\n"

    @property
    def value(self):
        return self.level * "\t" + self._func


# -------------------------------------------------------------------------------------------------
class PerformanceMapImplementation(ElementSerialization):
    def __init__(self, parent, header_entry, populates_self=False):
        super().__init__(parent, header_entry)
        if populates_self:
            self._func = f"{self._name}.populate_performance_map(this);\n"
        else:
            self._func = f"x.{self._name}.populate_performance_map(&x);\n"

    @property
    def value(self):
        return self.level * "\t" + self._func


# -------------------------------------------------------------------------------------------------
class GridAxisImplementation(ImplementationEntry):
    def __init__(self, name, parent):
        super().__init__(name, parent)
        self._func = [f"add_grid_axis(performance_map, {name});\n"]

    @property
    def value(self):
        entry = ""
        for f in self._func:
            entry += self.level * "\t" + f
        return entry


# -------------------------------------------------------------------------------------------------
class GridAxisFinalize(ImplementationEntry):
    def __init__(self, name, parent):
        super().__init__(name, parent)
        self._func = [f"performance_map->finalize_grid();\n"]

    @property
    def value(self):
        entry = ""
        for f in self._func:
            entry += self.level * "\t" + f
        return entry


# -------------------------------------------------------------------------------------------------
class DataTableImplementation(ImplementationEntry):
    def __init__(self, name, parent):
        super().__init__(name, parent)
        self._func = [f"add_data_table(performance_map, {name});\n"]

    @property
    def value(self):
        entry = ""
        for f in self._func:
            entry += self.level * "\t" + f
        return entry


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
    def __init__(self, name, parent):
        super().__init__(name, parent)
        self._func = f'return "{name}";'

    @property
    def value(self):
        entry = self.level * "\t" + self._func + "\n"
        return entry


# -------------------------------------------------------------------------------------------------
class CPPTranslator:
    def __init__(self):
        self._preamble = list()
        # defaultdict takes care of the factory base class
        self._implementations = defaultdict(lambda: ElementSerialization)
        self._implementations["grid_variables_base"] = GridAxisImplementation
        self._implementations["lookup_variables_base"] = DataTableImplementation
        self._implementations["performance_map_base"] = ElementSerialization

    def __str__(self):
        s = ""
        for p in self._preamble:
            s += p
        s += "\n"
        s += self._top_namespace.value
        s += "\n"
        return s

    def translate(self, container_class_name, header_tree):
        """X"""
        self._add_included_headers(header_tree._schema_name)

        # Create "root" node(s)
        self._top_namespace = ImplementationEntry(f"{container_class_name}")
        self._namespace = ImplementationEntry(f"{snake_style(header_tree._schema_name)}_ns", parent=self._top_namespace)

        self._get_items_to_serialize(header_tree.root)

    def _get_items_to_serialize(self, header_tree):
        for entry in header_tree.child_entries:
            # Shortcut to avoid creating "from_json" entries for the main class, but create them
            # for all other classes. The main class relies on an "Initialize" function instead,
            # dealt-with in the next block with function overrides.
            if isinstance(entry, Struct) and entry.name not in self._namespace._name:
                # Create the "from_json" function definition (header)
                s = StructSerialization(entry.name, self._namespace)
                for data_element_entry in [c for c in entry.child_entries if isinstance(c, DataElement)]:
                    # In function body, create each "get_to" for individual data elements
                    if "unique_ptr" in data_element_entry.type:
                        OwnedElementCreation(s, data_element_entry)
                    else:
                        OwnedElementSerialization(s, data_element_entry)
                    # In the special case of a performance_map subclass, add calls to its
                    # members' Populate_performance_map functions
                    if entry.superclass == "PerformanceMapBase":
                        PerformanceMapImplementation(data_element_entry.name, s)
            # Initialize static members
            if isinstance(entry, DataElementStaticMetainfo):
                DataElementStaticInitialization(entry, self._namespace)
            if isinstance(entry, InlineDependency):
                DependencyInitialization(entry, self._namespace)
            # Initialize and Populate overrides (Currently the only Member_function_override is the Initialize override)
            if isinstance(entry, MemberFunctionOverride):
                # Create the override function definition (header) using the declaration's signature
                m = MemberFunctionDefinition(entry, self._namespace)
                # Dirty hack workaround for Name() function
                if "Name" in entry.fname:
                    SimpleReturnProperty(entry.parent.name, m)
                else:
                    # In function body, choose element-wise ops based on the superclass
                    for data_element_entry in [c for c in entry.parent.child_entries if isinstance(c, DataElement)]:
                        if "unique_ptr" in data_element_entry.type:
                            ClassFactoryCreation(m, data_element_entry)
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
            # if isinstance(entry, CalculatePerformanceOverload):
            #     m = MemberFunctionDefinition(entry, self._namespace)
            #     for data_element_entry in [c for c in entry.parent.child_entries if isinstance(c, DataElement)]:
            #         # Build internals of Calculate_performance function
            #         if data_element_entry.name == "grid_variables":
            #             PerformanceOverloadImplementation(entry, m)
            # Lastly, handle the special case of objects that need both serialization
            # and initialization (currently a bit of a hack specific to this project)
            if isinstance(entry, ObjectSerializationDeclaration) and entry.name in self._namespace._name:
                s = FreeFunctionDefinition(entry, self._namespace)
                SerializeFromInitFunction("", s)
            else:
                self._get_items_to_serialize(entry)

    def _add_included_headers(self, main_header):
        self._preamble.clear()
        self._preamble.append(f"#include <{snake_style(main_header)}.h>\n#include <load-object.h>\n")
