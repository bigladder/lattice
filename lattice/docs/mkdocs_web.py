"""Build web documentation"""

from pathlib import Path
from shutil import copytree
import shutil
from urllib.parse import urlparse
from typing import List
from datetime import datetime

import pygit2
from jinja2 import Environment, FileSystemLoader
from mkdocs.__main__ import cli as mkdocs_cli

from ..file_io import (
    dump,
    load,
    dump_to_string,
    get_file_basename,
    make_dir,
    get_extension,
    translate,
)
from .process_template import process_template
from .grid_table import write_table


class DocumentFile:
    """Parse the components of a documentation file"""

    def __init__(self, path):
        """Set up DocumentFile attributes"""
        self.path = Path(path).absolute()
        self.file_base_name = get_file_basename(path, depth=2)
        self._markdown_output_path = None
        self._corresponding_schema_path = None

    @property
    def markdown_output_path(self):
        """Path to this DocumentFile's markdown output path"""
        return self._markdown_output_path

    @markdown_output_path.setter
    def markdown_output_path(self, path):
        self._markdown_output_path = Path(path).absolute()

    @property
    def corresponding_schema_path(self):
        """Path to this DocumentFile's corresponding schema path"""
        return self._corresponding_schema_path

    @corresponding_schema_path.setter
    def corresponding_schema_path(self, path):
        self._corresponding_schema_path = Path(path).name


class MkDocsWeb:  # pylint: disable=too-many-instance-attributes
    """Class that uses the mkdocs package to produce web documentation from schema"""

    def __init__(self, lattice):
        """Set up location and formatting parameters"""
        self.lattice = lattice
        self.build_directory = Path(self.lattice.web_docs_directory_path).absolute()
        self.docs_source_directory = Path(self.lattice.doc_templates_directory_path).absolute()
        self.docs_config_directory = Path(self.docs_source_directory, "web")
        self.source_schema_directory_path = self.lattice.schema_directory_path
        self.title = Path(self.docs_source_directory).parent.name
        self.description = ""
        self.author = ""
        self.colors = {"primary": "blue gray", "accent": "blue"}
        self.favicon_path = None
        self.logo_path = None
        self.setup_build_directory_structure()
        self.get_git_info()
        self.specification_order = None
        self.specification_counter = 1
        self.specification_templates: List[DocumentFile] = []
        self.navigation = []
        self.timestamp = datetime.now()

    def setup_build_directory_structure(self):  # pylint: disable=missing-function-docstring
        self.content_directory_path = make_dir(Path(self.build_directory, "docs"))
        self.output_directory_path = make_dir(Path(self.build_directory, "public"))
        self.assets_directory_path = make_dir(Path(self.content_directory_path, "assets"))

        # Content directories
        self.about_directory_path = make_dir(Path(self.content_directory_path, "about"))
        self.specifications_directory_path = make_dir(Path(self.content_directory_path, "specifications"))
        self.schema_directory_path = make_dir(Path(self.content_directory_path, "schema"))
        self.examples_directory_path = make_dir(Path(self.content_directory_path, "examples"))

    def get_git_info(self):  # pylint: disable=missing-function-docstring
        self.git_repo = pygit2.Repository(
            pygit2.discover_repository(self.docs_source_directory)  # pylint: disable=no-member
        )
        git_url = self.git_repo.remotes[0].url
        git_url_parts = urlparse(git_url)

        self.git_repo_name = Path(git_url_parts.path).stem
        self.git_repo_owner = Path(git_url_parts.path).parts[1]
        self.git_repo_host = Path(git_url_parts.netloc).stem
        if self.git_repo.head_is_detached:
            self.git_ref_name = "main"
        else:
            self.git_ref_name = self.git_repo.head.name
        self.git_remote_url = rf"https://{self.git_repo_host}.com/{self.git_repo_owner}/{self.git_repo_name}"
        self.base_url = rf"https://{self.git_repo_owner}.{self.git_repo_host}.io/{self.git_repo_name}/"

    # pylint: disable-next=missing-function-docstring, too-many-branches, too-many-statements

    def make_config(self):  # pylint: disable=missing-function-docstring
        favicon = (
            str(Path(self.favicon_path).relative_to(self.content_directory_path))
            if self.favicon_path is not None
            else None
        )
        logo = (
            str(Path(self.logo_path).relative_to(self.content_directory_path)) if self.logo_path is not None else None
        )
        return {
            "extra_css": ["assets/stylesheets/extra_styles.css"],
            "site_name": self.title,
            "site_url": self.base_url,
            "site_author": self.author,
            "site_description": self.description,
            "copyright": f"&copy {self.timestamp.year} {self.author} All rights reserved",
            "theme": {"name": "material", "favicon": favicon, "logo": logo, "palette": self.colors},
            "repo_name": self.git_repo_name,
            "repo_url": self.git_remote_url,
            "nav": self.navigation,
            "markdown_extensions": ["markdown_grid_tables", "pymdownx.smartsymbols", "def_list"],
        }

    def make_pages(self):
        # Check config directory
        about_page_content = None
        background_image_path = None
        config_path = None
        if Path(self.docs_config_directory).exists():
            for file in Path(self.docs_config_directory).iterdir():
                file_name = str(file)
                file_path = Path(self.docs_config_directory, file_name)
                if "about" in file_name:
                    with open(file_path, "r", encoding="utf-8") as file_in:
                        about_page_content = file_in.read()
                elif "logo" in file_name:
                    self.logo_path = file_path
                elif "config" in file_name:
                    config_path = file_path
                elif "favicon.ico" in file_name:
                    self.favicon_path = file_path

        if config_path is not None:
            config = load(config_path)
            if "title" in config:
                self.title = config["title"]
            if "author" in config:
                self.author = config["author"]
            if "description" in config:
                self.description = config["description"]
            if "specifications" in config:
                self.specification_order = config["specifications"]
            if "colors" in config:
                for item in config["colors"]:
                    self.colors[item] = config["colors"][item]

        if about_page_content is not None:
            self.make_main_menu_page(
                self.content_directory_path, "About", content=about_page_content, primary_index=True
            )

        if background_image_path is not None:
            shutil.copy(background_image_path, self.content_directory_path)
            if about_page_content is not None:
                shutil.copy(background_image_path, self.about_directory_path)

        if self.logo_path is not None:
            self.logo_path = str(shutil.copy(self.logo_path, self.assets_directory_path))

        if self.favicon_path is not None:
            self.favicon_path = str(shutil.copy(self.favicon_path, self.assets_directory_path))

        # Make stylesheets directory and copy extra_styles.css into this path.
        # Nesting inside stylesheets directory allows it to live with the other Mkdocs-generated css assets.
        self.style_css_dir = make_dir(Path(self.assets_directory_path, "stylesheets"))
        self.style_css_path = str(
            shutil.copy(Path(Path(__file__).parent.resolve(), "extra_styles.css"), self.style_css_dir)
        )

        # Specifications
        self.make_specification_pages()

        # Schema
        self.make_schema_page()

        # Examples
        self.make_examples_page()

    def make_specification_pages(self):  # pylint: disable=missing-function-docstring

        # Collect list of doc template files
        if self.specification_order is not None:
            for specification_name in self.specification_order:
                file_name = f"{specification_name}.md.j2"
                file_path = Path(self.docs_source_directory, file_name)
                if file_path.exists():
                    self.specification_templates.append(DocumentFile(file_path))
                else:
                    raise Exception(
                        f'Unable to find specification file, "{file_path}", ' "referenced in configuration."
                    )
        else:
            for file in Path(self.docs_source_directory).iterdir():
                file_path = Path(self.docs_source_directory, file)
                if file_path.is_file():
                    self.specification_templates.append(DocumentFile(file_path))

        # Identify corresponding schema files
        for template in self.specification_templates:
            for schema_file in Path(self.source_schema_directory_path).iterdir():
                if template.file_base_name in str(schema_file):
                    file_path = Path(self.source_schema_directory_path, schema_file)
                    template.corresponding_schema_path = file_path

        # Process templates
        sub_page_list = []
        for template in self.specification_templates:
            template.markdown_output_path = Path(
                self.specifications_directory_path, f"{get_file_basename(template.path, depth=2)}.md"
            )

            sub_page_list.append(
                self.make_specification_page(
                    template.path,
                    template.markdown_output_path,
                    self.source_schema_directory_path,
                    template.corresponding_schema_path,
                )
            )

        if len(sub_page_list) == 1:
            page_path = [v for _, v in sub_page_list[0].items()][0]
            self.navigation.append({"Specification": page_path})
        else:
            self.navigation.append({"Specifications": sub_page_list})

    def make_schema_page(self):  # pylint: disable=missing-function-docstring
        schema_files = {"Schema": [], "Description": []}
        schema_assets_directory = Path(self.schema_directory_path, "assets")
        make_dir(schema_assets_directory)
        references = {}
        reference_counter = 1
        reference_string = "\n"
        for schema in self.lattice.schemas:
            content = load(schema.json_schema_path)
            output_path = Path(schema_assets_directory, get_file_basename(schema.json_schema_path))
            shutil.copy(schema.json_schema_path, output_path)
            references[reference_counter] = str(Path(output_path).relative_to(self.schema_directory_path))
            schema_files["Schema"].append(f"[{content['title']}][{reference_counter}]")
            reference_string += f"\n[{reference_counter}]: {references[reference_counter]}"
            reference_counter += 1
            schema_files["Description"].append(content["description"])

        content = "# JSON Schema\n\n" + write_table(schema_files, ["Schema", "Description"]) + reference_string + "\n"
        self.make_main_menu_page(self.schema_directory_path, "Schema", content=content)

    def make_examples_page(self):  # pylint: disable=missing-function-docstring
        example_files = {"File Name": [], "Description": [], "Download": []}
        example_assets_directory = Path(self.examples_directory_path, "assets")
        make_dir(example_assets_directory)
        references = {}
        reference_counter = 1
        reference_string = "\n"
        for example in self.lattice.examples:
            content = load(example)
            file_base_name = get_file_basename(example, depth=1)
            formats = ["yaml", "json", "cbor"]
            output_path = {}
            web_links = {}
            for fmt in formats:
                output_path[fmt] = Path(example_assets_directory, f"{file_base_name}.{fmt}")
                references[reference_counter] = str(Path(output_path[fmt]).relative_to(self.examples_directory_path))
                web_links[fmt] = f"[{fmt.upper()}][{reference_counter}]"
                reference_string += f"\n[{reference_counter}]: {references[reference_counter]}"
                reference_counter += 1
                translate(example, output_path[fmt])
            example_files["File Name"].append(file_base_name)
            if "metadata" in content:
                example_files["Description"].append(content["metadata"]["description"])
            else:
                example_files["Description"].append('No description: Example has no "metadata" element.')
            example_files["Download"].append(f"{web_links['yaml']} {web_links['json']} {web_links['cbor']}")

        content = (
            "# Example Files\n\n"
            + write_table(example_files, ["File Name", "Description", "Download"])
            + reference_string
            + "\n"
        )
        self.make_main_menu_page(self.examples_directory_path, "Examples", content=content)

    @staticmethod
    def make_page(page_path, front_matter, content=""):  # pylint: disable=missing-function-docstring
        with open(page_path, "w", encoding="utf-8") as file:
            file.writelines(f"{make_front_matter(front_matter)}{content}")

    # pylint: disable-next=missing-function-docstring, too-many-arguments
    def make_main_menu_page(
        self,
        page_dir_path,
        title,
        content="",
        schema_path=None,
        content_type=None,
        content_path=None,
        sub_page_list=None,
        primary_index=False,
    ):
        front_matter = {
            "title": title,
            "build_date_utc": self.timestamp,
        }

        if content_type is not None:
            front_matter["type"] = content_type

        if schema_path is not None:
            front_matter["github_schema"] = schema_path

        if content_path is not None:
            front_matter["github_content"] = content_path

        file_name = "index.md" if primary_index else f"{title.lower().replace(' ','-')}.md"

        if sub_page_list is None:
            page_path = Path(page_dir_path, file_name)
            self.navigation.append({title: str(page_path.relative_to(self.content_directory_path))})
        else:
            page_path = Path(page_dir_path, "index.md")
            self.navigation.append({title: [str(page_path.relative_to(self.content_directory_path))] + sub_page_list})
        MkDocsWeb.make_page(page_path, front_matter, content)

    def make_specification_page(
        self,  # pylint: disable=missing-function-docstring
        template_path,
        output_path,
        schema_dir_path,
        corresponding_schema_path=None,
    ):
        """
        Returns dictionary to append to sub_page list.
        """
        if get_extension(template_path) == ".j2":
            # Process template
            process_template(template_path, output_path, schema_dir=schema_dir_path)
        else:
            copytree(template_path, output_path)

        title = get_file_basename(template_path, depth=2)

        # Append front matter
        front_matter = {
            "title": title,
            "build_date_utc": self.timestamp,
        }

        self.specification_counter += 1

        template_relative_path = Path(template_path).name

        if corresponding_schema_path is None:
            corresponding_schema_path = schema_dir_path

        front_matter["github_schema"] = corresponding_schema_path

        front_matter["github_content"] = template_relative_path

        with open(output_path, "r", encoding="utf-8") as original_file:
            content = original_file.read()
        MkDocsWeb.make_page(output_path, front_matter, content)
        return {title: str(output_path.relative_to(self.content_directory_path))}

    def build(self):
        """Build documentation"""

        self.make_pages()

        # Setup Config
        config_file_path = Path(self.build_directory, "mkdocs.yml")
        dump(self.make_config(), config_file_path)

        mkdocs_cli(
            ["build", "--config-file", str(config_file_path), "--site-dir", str(self.output_directory_path)],
            standalone_mode=False,
        )


def make_front_matter(front_matter):  # pylint: disable=missing-function-docstring
    return f"---\n{dump_to_string(front_matter,'yaml')}---\n\n"


def prepend_file_content(file_path, new_content):  # pylint: disable=missing-function-docstring
    with open(file_path, "r", encoding="utf-8") as original_file:
        original_content = original_file.read()
    with open(file_path, "w", encoding="utf-8") as modified_file:
        modified_file.write(new_content + original_content)


def render_template(template_path, output_path, values):  # pylint: disable=missing-function-docstring
    template_directory_path = Path(template_path).parent.absolute()
    template_environment = Environment(loader=FileSystemLoader(template_directory_path))
    template = template_environment.get_template(Path(template_path).name)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(template.render(**values))
