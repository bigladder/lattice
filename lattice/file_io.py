"""Wrapper functions for commonly-used file manipulations"""

import json
import os
import shutil
from pathlib import Path

import cbor2
import yaml


def get_extension(file) -> str:
    """Return the last suffix of a filename"""
    if isinstance(file, Path):
        return file.suffix
    return os.path.splitext(file)[1]


def get_file_basename(file, depth=0) -> str:
    """Return file's base name; i.e. the name with 'depth' suffixes removed"""
    basename = os.path.basename(file)
    for i in range(depth):  # pylint: disable=unused-variable
        basename = os.path.splitext(basename)[0]
    return basename


def get_base_stem(file: Path) -> str:
    """Return the file's base name, with all suffixes removed"""
    return file.name.partition(".")[0]


def load(input_file_path) -> dict:
    """Return the contents of data file"""
    ext = get_extension(input_file_path).lower()
    if ext == ".json":
        with open(input_file_path, "r", encoding="utf-8") as input_file:
            return json.load(input_file)
    elif ext == ".cbor":
        with open(input_file_path, "rb", encoding="utf-8") as input_file:
            return cbor2.load(input_file)
    elif ext in [".yaml", ".yml"]:
        with open(input_file_path, "r", encoding="utf-8") as input_file:
            return yaml.load(input_file, Loader=yaml.CLoader)
    else:
        raise ValueError(f'Unsupported input "{ext}".')


def dump(content: dict, output_file_path: Path | str) -> None:
    """Write a dictionary as a data file."""
    ext = get_extension(output_file_path).lower()
    if ext == ".json":
        with open(output_file_path, "w", encoding="utf-8") as output_file:
            json.dump(content, output_file, indent=4)
    elif ext == ".cbor":
        with open(output_file_path, "wb") as output_file:
            cbor2.dump(content, output_file)
    elif ext in [".yaml", ".yml"]:
        with open(output_file_path, "w", encoding="utf-8") as out_file:
            yaml.dump(content, out_file, sort_keys=False)
    else:
        raise ValueError(f'Unsupported output "{ext}".')


def dump_to_string(content: dict, output_type="json"):
    """Write a dictionary as a string"""
    if output_type == "json":
        return json.dumps(content, indent=4)
    if output_type in ["yaml", "yml"]:
        return yaml.dump(content, sort_keys=False)
    raise ValueError(f'Unsupported output "{output_type}".')


def string_to_file(contents: str, output_file_path: Path):
    """Write a string to file"""
    with open(output_file_path, "w", encoding="utf-8") as dest:
        dest.write(contents)
        dest.write("\n")


def translate(input_file, output_file):
    """Translate between data file types"""
    dump(load(input_file), output_file)


def make_dir(dir_path):
    """Return a newly-created directory path"""
    if isinstance(dir_path, Path):
        Path.mkdir(dir_path, exist_ok=True)
    elif not os.path.exists(dir_path):
        os.mkdir(dir_path)
    return dir_path


def remove_dir(dir_path):
    """Remove existing directory path"""
    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        shutil.rmtree(dir_path)


def check_dir(dir_path, dir_description="Directory"):
    """Returns if a path both exists and is a directory"""
    if not os.path.exists(dir_path):
        raise FileNotFoundError(f'{dir_description}, "{dir_path}", does not exist.')
    if not os.path.isdir(dir_path):
        raise FileNotFoundError(f'{dir_description}, "{dir_path}", is not a directory.')


def check_executable(name, install_url):
    """Return if the named executable exists in system paths."""
    if shutil.which(name) is None:
        raise FileNotFoundError(f'Unable to find "{name}". To install, go to {install_url}.')
