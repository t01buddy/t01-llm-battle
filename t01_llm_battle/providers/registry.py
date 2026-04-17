import importlib
import importlib.util
import sys
from pathlib import Path

from .base import BaseProvider

# Built-in provider module names (relative to this package)
_BUILTIN_MODULES = [
    "t01_llm_battle.providers.openai",
    "t01_llm_battle.providers.anthropic",
    "t01_llm_battle.providers.google",
    "t01_llm_battle.providers.groq",
    "t01_llm_battle.providers.openrouter",
    "t01_llm_battle.providers.ollama",
]

_USER_PLUGIN_DIR = Path.home() / ".t01-llm-battle" / "providers"

_registry: dict[str, BaseProvider] = {}


def _load_module_providers(module) -> None:
    """Find all BaseProvider subclasses in a module and register them."""
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        try:
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseProvider)
                and obj is not BaseProvider
                and hasattr(obj, "name")
            ):
                instance = obj()
                _registry[instance.name] = instance
        except Exception:
            pass


def load_providers() -> None:
    """Load built-in providers and user plugins into the registry."""
    _registry.clear()

    # Built-ins (skip if module not yet implemented)
    for module_name in _BUILTIN_MODULES:
        try:
            mod = importlib.import_module(module_name)
            _load_module_providers(mod)
        except ModuleNotFoundError:
            pass  # provider not yet implemented — skip
        except Exception as e:
            print(f"[registry] warning: failed to load {module_name}: {e}")

    # User plugins
    if _USER_PLUGIN_DIR.exists():
        for py_file in sorted(_USER_PLUGIN_DIR.glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[py_file.stem] = mod
                spec.loader.exec_module(mod)
                _load_module_providers(mod)
            except Exception as e:
                print(f"[registry] warning: failed to load plugin {py_file.name}: {e}")


def get_provider(name: str) -> BaseProvider:
    """Get a provider by name. Raises KeyError if not found."""
    if not _registry:
        load_providers()
    if name not in _registry:
        raise KeyError(f"Unknown provider: {name!r}. Available: {list(_registry.keys())}")
    return _registry[name]


def list_providers() -> list[str]:
    """Return names of all loaded providers."""
    if not _registry:
        load_providers()
    return sorted(_registry.keys())
