from dataclasses import dataclass
from lattice.cpp.header_entries import HeaderEntry
from lattice.cpp.header_entries import register_data_element_operation

@dataclass
class GridVarCounterEnum(HeaderEntry):
    elements_dict: dict

    def __post_init__(self):
        super().__post_init__()
        self.type = "enum"
        self._closure = "};"
        self._enumerants = list()

        for element in self.elements_dict:
            self._enumerants.append(f"{element}_index")
        self._enumerants.append("index_count");

    def __str__(self):
        enums = self._enumerants
        entry = f"{self._indent}{self.type} {self._opener}\n"
        entry += ",\n".join([f"{self._indent}\t{e}" for e in enums])
        entry += f"\n{self._indent}{self._closure}"
        return entry

def register():
    register_data_element_operation("GridVariablesTemplate", GridVarCounterEnum)