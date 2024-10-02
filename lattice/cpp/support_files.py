from jinja2 import Template
import os
import sys
from lattice.file_io import dump
from lattice.util import snake_style, hyphen_separated_lowercase_style
from pathlib import Path
from lattice.header_entries import InitializeFunction, Struct


def support_header_pathnames(output_directory: Path):
    """Return a list of the template-generated header file names."""
    return [
        output_directory / "-".join(snake_style(template.stem).split("_"))
        for template in Path(__file__).with_name("templates").iterdir()
        if ".h" in template.suffixes
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


def generate_superclass_header(superclass: str, output_directory: Path):
    s1 = f"#ifndef {superclass.upper()}_H_"
    s2 = f"#define {superclass.upper()}_H_"
    s3 = f"#endif"

    class_entry = Struct(superclass, None)
    initialize_fn = InitializeFunction(None, class_entry)

    superclass_contents = f"{s1}\n{s2}\n{class_entry.value}\n{s3}"

    header = Path(output_directory / f"{hyphen_separated_lowercase_style(superclass)}.h")
    if not header.exists():
        dump(superclass_contents, header)