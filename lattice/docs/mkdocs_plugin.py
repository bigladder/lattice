"""MkDocs plugin that drives lattice's web documentation generation.

Registering this plugin (instead of calling `Lattice.generate_web_documentation()`
once, ahead of an isolated `mkdocs build`) lets content generation run as part of
MkDocs's own build/serve lifecycle, so both `mkdocs build` and `mkdocs serve` -
including its live-reload rebuilds - always regenerate from the current source
state instead of serving whatever happened to be on disk from an earlier run.
"""

from pathlib import Path

from mkdocs.config import config_options
from mkdocs.plugins import BasePlugin

from ..lattice import Lattice
from .mkdocs_web import MkDocsWeb


class LatticePlugin(BasePlugin):
    """Regenerates a project's lattice-derived web docs on every MkDocs build or serve."""

    config_scheme = (("root_directory", config_options.Type(str, default=".")),)

    def on_config(self, config, **kwargs):  # pylint: disable=unused-argument
        root_directory = Path(self.config["root_directory"]).resolve()
        self.lattice = Lattice(root_directory=root_directory)
        self.web_docs = MkDocsWeb(self.lattice)
        self.web_docs.make_pages(config)

        config["nav"] = self.web_docs.navigation
        return config

    def on_serve(self, server, *, config, builder):  # pylint: disable=unused-argument
        # The generated docs_dir is rewritten on every build (see on_config above), so
        # watching it would trigger an endless rebuild loop. Watch the actual sources instead:
        # schema, examples, and the doc/template directory (which also holds docs/web/*, e.g.
        # about.md) - so edits to any of them trigger a live-reload rebuild.
        docs_dir = Path(config["docs_dir"])
        server.unwatch(str(docs_dir))

        for source_path in (
            self.lattice.schema_directory_path,
            self.lattice.example_directory_path,
            self.lattice.doc_templates_directory_path,
        ):
            if source_path and Path(source_path).exists():
                server.watch(str(source_path))

        return server
