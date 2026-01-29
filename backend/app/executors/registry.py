"""Executor plugin registry with dynamic loading."""

import importlib
import pkgutil
import logging
from typing import Dict, Type, List, Optional
from pathlib import Path

from app.executors.spec import ExecutorAdapter, ExecutorMetadata, ExecutorNotFoundError

logger = logging.getLogger(__name__)


class ExecutorRegistry:
    """Registry for executor plugins with dynamic loading."""

    _adapters: Dict[str, Type[ExecutorAdapter]] = {}
    _instances: Dict[str, ExecutorAdapter] = {}
    _loaded: bool = False

    @classmethod
    def register(cls, name: str):
        """Decorator to register an executor adapter.

        Usage:
            @ExecutorRegistry.register("claude")
            class ClaudeAdapter(ExecutorAdapter):
                ...
        """
        def decorator(adapter_class: Type[ExecutorAdapter]):
            if name in cls._adapters:
                logger.warning(f"Overwriting existing executor adapter: {name}")
            cls._adapters[name] = adapter_class
            logger.info(f"Registered executor adapter: {name}")
            return adapter_class
        return decorator

    @classmethod
    def get(cls, name: str) -> ExecutorAdapter:
        """Get an executor adapter instance by name.

        Args:
            name: Executor name (e.g., "claude", "cursor")

        Returns:
            ExecutorAdapter instance

        Raises:
            ExecutorNotFoundError: If executor not registered
        """
        # Ensure plugins are loaded
        if not cls._loaded:
            cls.load_all_plugins()

        if name not in cls._adapters:
            raise ExecutorNotFoundError(
                f"Unknown executor: {name}. Available: {list(cls._adapters.keys())}"
            )

        # Return cached instance or create new
        if name not in cls._instances:
            cls._instances[name] = cls._adapters[name]()

        return cls._instances[name]

    @classmethod
    async def get_available(cls) -> List[ExecutorMetadata]:
        """List all available executors (installed and accessible).

        Returns:
            List of ExecutorMetadata for available executors
        """
        if not cls._loaded:
            cls.load_all_plugins()

        available = []
        for name, adapter_class in cls._adapters.items():
            try:
                adapter = cls.get(name)
                if await adapter.is_available():
                    available.append(adapter.get_metadata())
            except Exception as e:
                logger.warning(f"Failed to check availability of {name}: {e}")

        return available

    @classmethod
    def list_all(cls) -> List[ExecutorMetadata]:
        """List all registered executors (may not be installed).

        Returns:
            List of ExecutorMetadata for all registered executors
        """
        if not cls._loaded:
            cls.load_all_plugins()

        all_executors = []
        for name, adapter_class in cls._adapters.items():
            try:
                adapter = cls.get(name)
                all_executors.append(adapter.get_metadata())
            except Exception as e:
                logger.warning(f"Failed to get metadata for {name}: {e}")

        return all_executors

    @classmethod
    def load_all_plugins(cls):
        """Load all executor plugins from adapters and plugins directories."""
        if cls._loaded:
            return

        logger.info("Loading executor plugins...")

        # Load built-in adapters
        cls._load_plugins_from_package("app.executors.adapters")

        # Load community plugins
        cls._load_plugins_from_package("app.executors.plugins")

        cls._loaded = True
        logger.info(f"Loaded {len(cls._adapters)} executor plugins")

    @classmethod
    def _load_plugins_from_package(cls, package_name: str):
        """Load all Python modules from a package.

        Args:
            package_name: Package name (e.g., "app.executors.adapters")
        """
        try:
            package = importlib.import_module(package_name)
            package_path = Path(package.__file__).parent

            for finder, name, ispkg in pkgutil.iter_modules([str(package_path)]):
                if name.startswith("_"):
                    continue

                module_name = f"{package_name}.{name}"
                try:
                    importlib.import_module(module_name)
                    logger.debug(f"Loaded plugin module: {module_name}")
                except Exception as e:
                    logger.error(f"Failed to load plugin {module_name}: {e}")

        except ImportError as e:
            logger.warning(f"Package {package_name} not found: {e}")

    @classmethod
    def reload_plugins(cls):
        """Reload all plugins (useful for development)."""
        cls._adapters.clear()
        cls._instances.clear()
        cls._loaded = False
        cls.load_all_plugins()

    @classmethod
    def unregister(cls, name: str):
        """Unregister an executor adapter.

        Args:
            name: Executor name to unregister
        """
        if name in cls._adapters:
            del cls._adapters[name]
        if name in cls._instances:
            del cls._instances[name]
        logger.info(f"Unregistered executor adapter: {name}")


# Convenience functions

def get_executor(name: str) -> ExecutorAdapter:
    """Get an executor adapter by name.

    Args:
        name: Executor name

    Returns:
        ExecutorAdapter instance
    """
    return ExecutorRegistry.get(name)


async def list_available_executors() -> List[ExecutorMetadata]:
    """List all available executors.

    Returns:
        List of ExecutorMetadata
    """
    return await ExecutorRegistry.get_available()


def list_all_executors() -> List[ExecutorMetadata]:
    """List all registered executors.

    Returns:
        List of ExecutorMetadata
    """
    return ExecutorRegistry.list_all()
