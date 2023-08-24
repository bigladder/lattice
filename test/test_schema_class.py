from lattice.schema import Schema
import pathlib

def test_schema():
  schema_file = Schema(pathlib.Path("examples","fan_spec","schema","RS0003.schema.yaml"))
  for data_group in schema_file.data_groups:
    print(f"\nData Group: {data_group.name}")
    for data_element in data_group.data_elements:
      print(f"  {data_element.name}")
  for enumeration in schema_file.enumerations:
    print(f"\nEnumeration: {enumeration.name}")
    for enumerator in enumeration.enumerators:
      print(f"  {enumerator.name}")
