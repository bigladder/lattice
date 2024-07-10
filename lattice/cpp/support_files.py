from jinja2 import Template
import os
import sys
from lattice.file_io import dump
from lattice.util import snake_style
from pathlib import Path


def support_header_pathnames(output_directory: Path):
    """Return a list of the template-generated header file names."""
    return [
        output_directory / "-".join(snake_style(template.stem).split("_"))
        for template in Path(__file__).with_name("templates").iterdir() if ".h" in template.suffixes
    ]

def render_support_headers(namespace_name: str, output_directory: Path):
    """Generate the project-specific helper headers."""
    for template in Path(__file__).with_name("templates").iterdir():
        if ".h" in template.suffixes:
            header = Template(template.read_text())
            generated_file_name = "-".join(snake_style(template.stem).split("_"))
            dump(
                header.render(namespace=namespace_name),
                Path(output_directory) / generated_file_name,
            )

def render_build_files(project_name: str, submodules: list, output_directory: Path):
    """Generate the project-specific CMakeLists files."""
    generated_file_name = "CMakeLists.txt"

    project_cmake_file = Path(__file__).with_name("templates") / "project-cmake.txt.j2"
    if project_cmake_file.exists():
        cmake_project = Template(project_cmake_file.read_text())
        dump(
            cmake_project.render(project_name=project_name),
            Path(output_directory) / generated_file_name,
        )
    src_cmake_file = Path(__file__).with_name("templates") / "project-src-cmake.txt.j2"
    if src_cmake_file.exists():
        src_cmake = Template(src_cmake_file.read_text())
        dump(
            src_cmake.render(project_name=project_name),
            Path(output_directory) / "src" / generated_file_name,
        )
    vendor_cmake_file = Path(__file__).with_name("templates") / "project-vendor-cmake.txt.j2"
    if vendor_cmake_file.exists():
        vendor_cmake = Template(vendor_cmake_file.read_text())
        submodule_names = [Path(submodule).stem for submodule in submodules]
        print(submodule_names)
        dump(
            vendor_cmake.render(submodules=submodule_names),
            Path(output_directory) / "vendor" / generated_file_name,
        )
