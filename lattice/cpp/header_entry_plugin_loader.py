import importlib
from pathlib import Path

"""From https://github.com/ArjanCodes/2021-plugin-architecture/blob/main/after/game/loader.py"""

class ModuleInterface:
    """Represents a plugin interface. A plugin has a single register function."""

    @staticmethod
    def register() -> None:
        """Register the necessary items in the game character factory."""


def import_module(name: str) -> ModuleInterface:
    """Imports a module given a name."""
    return importlib.import_module(name)  # type: ignore


def load_plugins(plugins: Path) -> None:
    """Loads the plugins defined in the plugins list."""
    for plugin_file in plugins.iterdir():
        plugin = import_module(plugin_file.stem) #TODO: not robust?
        plugin.register()