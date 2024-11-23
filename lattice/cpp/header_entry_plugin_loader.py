from importlib import util
from pathlib import Path

"""From https://github.com/ArjanCodes/2021-plugin-architecture/blob/main/after/game/loader.py"""

class ModuleInterface:
    """Represents a plugin interface. A plugin has a single register function."""

    @staticmethod
    def register() -> None:
        """Register the necessary items in the game character factory."""


def import_module(path: Path) -> ModuleInterface:
    """Imports a module given a name."""
    name = path.stem
    spec = util.spec_from_file_location(name, path)
    try:
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except:
        raise ModuleNotFoundError

def load_plugins(plugins: Path) -> None:
    """Loads the plugins defined in the plugins list."""
    for plugin_file in plugins.iterdir():
        plugin = import_module(plugin_file) #TODO: not robust?
        plugin.register()