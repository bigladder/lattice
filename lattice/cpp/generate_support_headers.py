from jinja2 import Template
import os
import sys
from lattice.file_io import dump
from lattice.util import snake_style
from pathlib import Path

def support_header_pathnames(output_directory: Path):
    return [output_directory / "-".join(snake_style(template.stem).split("_")) for template in Path(__file__).with_name("templates").iterdir()]

def generate_support_headers(namespace_name: str, root_data_groups: list[str], output_directory: Path):
    for template in Path(__file__).with_name("templates").iterdir():
        enum_info = Template(template.read_text())
        generated_file_name = "-".join(snake_style(template.stem).split("_"))
        dump(enum_info.render(namespace=namespace_name, root_objects=root_data_groups), Path(output_directory) / generated_file_name)

