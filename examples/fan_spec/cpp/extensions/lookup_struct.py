import re
from dataclasses import dataclass
from lattice.cpp.header_entries import DataElement, HeaderEntry
from lattice.cpp.header_entries import register_data_group_operation

@dataclass
class LookupStruct(HeaderEntry):
    """
    Special case struct for Lookup Variables. Its str overload adds a LookupStruct declaration.
    """
    def __post_init__(self):
        super().__post_init__()
        self.name = f"{self.name}Struct"
        self.type = "struct"
        self._closure = "};"

        self.trace()

    def __str__(self):
        # Add a LookupStruct that offers a SOA access rather than AOS
        struct = f"{self._indent}{self.type} {self.name} {self._opener}\n"
        for c in [ch for ch in self.child_entries if isinstance(ch, DataElement)]:
            m = re.match(r'std::vector\<(.*)\>', c.type)
            assert m is not None
            struct += f"{self._indent}\t{m.group(1)} {c.name};\n"
        struct += f"{self._indent}{self._closure}"

        return struct

def register():
    register_data_group_operation("LookupVariablesTemplate", LookupStruct)
