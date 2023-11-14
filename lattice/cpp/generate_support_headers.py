from jinja2 import Template
import os
import sys
from lattice.file_io import dump
from lattice.util import snake_style
from pathlib import Path

# file_loader = FileSystemLoader(os.path.join(os.path.dirname(__file__), 'generation_templates'))
# env = Environment(loader=file_loader)

def generate_support_headers(namespace_name: str, output_directory: Path):
    for template in Path(__file__).with_name("templates").iterdir():
        enum_info = Template(template.read_text())
        generated_file_name = "-".join(snake_style(template.stem).split("_"))
        dump(enum_info.render(namespace=namespace_name), Path(output_directory) / generated_file_name)

