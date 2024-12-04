import re
from dataclasses import dataclass
from lattice.cpp.header_entries import DataElement, Struct
from lattice.cpp.header_entries import register_data_group_operation

@dataclass
class LookupStruct(Struct):
    """
    Special case struct for Lookup Variables. Its str overload adds a LookupStruct declaration.
    """

    def __str__(self):
        """Two C++ entries share the schema child-entries, so one HeaderEntry subclass creates both."""
        struct = super().__str__()

        # Add a LookupStruct that offers a SOA access rather than AOS
        tab = "\t"
        struct += "\n"
        struct += f"{self._level * tab}{self.type} {self.name}Struct {self._opener}\n"
        for c in [ch for ch in self.child_entries if isinstance(ch, DataElement)]:
            m = re.match(r'std::vector\<(.*)\>', c.type)
            assert m is not None
            struct += f"{(self._level+1) * tab}{m.group(1)} {c.name};\n"
        struct += f"{self._level * tab}{self._closure}"

        return struct

def register():
    register_data_group_operation("LookupVariablesTemplate", LookupStruct)