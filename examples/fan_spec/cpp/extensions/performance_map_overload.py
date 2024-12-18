import re
from dataclasses import dataclass, field
from lattice.cpp.header_entries import DataElement, Struct, HeaderEntry, FunctionalHeaderEntry
from lattice.cpp.header_translator import PluginInterface

def remove_prefix(text, prefix):
    return text[len(prefix) :] if text.startswith(prefix) else text

@dataclass
class PerformanceMapOverload(FunctionalHeaderEntry):
    """ """
    name: str = field(init=False, default="")
    _f_name: str = field(init=False)

    def __post_init__(self):
        self._f_name = "calculate_performance"
        self.args = f"({', '.join(self._f_args)})"
        super().__post_init__()

    def __str__(self):
        complete_decl = self._indent + "using PerformanceMapTemplate::calculate_performance;\n"
        complete_decl += self._indent + " ".join([self._f_ret, self._f_name, self.args]) + self._closure
        return complete_decl

class PerformanceOverloadPlugin(PluginInterface, base_class="PerformanceMapTemplate"):
    """"""
    def process_data_group(self, parent_node: HeaderEntry):
        for entry in parent_node.child_entries:
            if isinstance(entry, Struct) and entry.superclass == "PerformanceMapTemplate" and entry.parent:
                for lvstruct in [
                    lv
                    for lv in entry.parent.child_entries
                    if isinstance(lv, Struct) and lv.superclass == "LookupVariablesTemplate"
                    and remove_prefix(lv.name, "LookupVariables") == remove_prefix(entry.name, "PerformanceMap")
                ]:
                    f_ret = f"{lvstruct.name}Struct"
                    n_ret = len([c for c in lvstruct.child_entries if isinstance(c, DataElement)])
                    # for each performance map, find GridVariables sibling of PerformanceMap, that has a matching name
                    for gridstruct in [
                        gridv
                        for gridv in entry.parent.child_entries
                        if isinstance(gridv, Struct) and gridv.superclass == "GridVariablesTemplate"
                        and remove_prefix(gridv.name, "GridVariables") == remove_prefix(entry.name, "PerformanceMap")
                    ]:
                        f_args = list()
                        for ce in [c for c in gridstruct.child_entries if isinstance(c, DataElement)]:
                            f_args.append(" ".join(["double", ce.name]))
                        f_args.append("Btwxt::Method performance_interpolation_method = Btwxt::Method::LINEAR")
                        PerformanceMapOverload(entry, f_ret, f_args)
            else:
                self.process_data_group(entry)
