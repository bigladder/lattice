from importlib import util
from pathlib import Path
from .header_entries import HeaderEntry
from typing import Callable

"""From https://github.com/ArjanCodes/2021-plugin-architecture/blob/main/after/game/loader.py"""


class ModuleInterface:

    # @staticmethod
    # def insert_entry(root: HeaderEntry) -> None:
    #     """
    #     For a given Data Group Template, insert code into the necessary parts of the HeaderEntry tree.
    #     """

    @staticmethod
    def register() -> None:
        """Register the necessary items in the game character factory."""


def import_module(path: Path):
    """Imports a module given a path."""
    spec = util.spec_from_file_location(path.stem, path)
    try:
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except:
        raise ModuleNotFoundError


def load_extensions(from_path: Path) -> None:
    """Loads the plugins defined in the plugins list."""
    if from_path.is_dir():
        for plugin_file in [x for x in from_path.iterdir() if x.suffix == ".py"]:
            plugin = import_module(plugin_file)
            #plugin.register()

