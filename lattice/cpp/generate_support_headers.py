from jinja2 import Template
import os
import sys
from lattice.file_io import dump
from lattice.util import snake_style
from pathlib import Path


def support_header_pathnames(output_directory: Path):
    return [
        output_directory / "-".join(snake_style(template.stem).split("_"))
        for template in Path(__file__).with_name("templates").iterdir()
    ]


def generate_support_headers(namespace_name: str, root_data_groups: list[str], output_directory: Path):
    for template in Path(__file__).with_name("templates").iterdir():
        if ".h" in template.suffixes:
            enum_info = Template(template.read_text())
            generated_file_name = "-".join(snake_style(template.stem).split("_"))
            dump(
                enum_info.render(namespace=namespace_name, root_objects=root_data_groups),
                Path(output_directory) / generated_file_name,
            )


def generate_build_support(project_name: str, submodules: list, output_directory: Path):
    generated_file_name = "CMakeLists.txt"

    project_cmake_file = Path(__file__).with_name("templates") / "project-cmake.txt.j2"
    if project_cmake_file.exists():
        enum_info = Template(project_cmake_file.read_text())
        dump(
            enum_info.render(project_name=project_name),
            Path(output_directory) / generated_file_name,
        )
    src_cmake_file = Path(__file__).with_name("templates") / "project-src-cmake.txt.j2"
    if src_cmake_file.exists():
        enum_info = Template(src_cmake_file.read_text())
        dump(
            enum_info.render(project_name=project_name),
            Path(output_directory) / "src" / generated_file_name,
        )
    vendor_cmake_file = Path(__file__).with_name("templates") / "project-vendor-cmake.txt.j2"
    if vendor_cmake_file.exists():
        enum_info = Template(vendor_cmake_file.read_text())
        submodule_names = [Path(submodule).stem for submodule in submodules]
        print(submodule_names)
        dump(
            enum_info.render(submodules=submodule_names),
            Path(output_directory) / "vendor" / generated_file_name,
        )
