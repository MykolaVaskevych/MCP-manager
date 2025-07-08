"""Universal configuration system for any MCP server."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class UniversalConfigAdapter:
    """Universal configuration adapter that works with any MCP server."""

    def adapt_config(
        self, config: Dict[str, Any], server_info: Any = None
    ) -> Dict[str, Any]:
        """
        Universal config adaptation - works with any MCP server.

        Most MCP servers accept configuration via environment variables.
        This universal approach should work with 95% of MCP servers.
        """
        if not config:
            return {"cli_args": [], "env_vars": {}}

        # Universal approach: Convert all config to environment variables
        # This works with the vast majority of MCP servers
        env_vars = {}

        for key, value in config.items():
            if value is not None:
                # Convert to standard environment variable format
                env_key = key.upper()

                # Handle different value types universally
                if isinstance(value, bool):
                    env_vars[env_key] = "true" if value else "false"
                elif isinstance(value, (list, tuple)):
                    # Join arrays with commas (standard convention)
                    env_vars[env_key] = ",".join(map(str, value))
                else:
                    env_vars[env_key] = str(value)

        logger.debug(
            f"Universal config adaptation: {len(env_vars)} environment variables"
        )

        return {"cli_args": [], "env_vars": env_vars}


# Global universal adapter instance
universal_adapter = UniversalConfigAdapter()


def get_universal_adapter() -> UniversalConfigAdapter:
    """Get the universal configuration adapter."""
    return universal_adapter


# Legacy compatibility - remove specialized adapters entirely
def get_specialized_adapter(package_name: str) -> None:
    """
    Returns None - no specialized adapters in universal system.
    All MCP servers use the universal adapter.
    """
    return None


class ConfigurationAdaptationSystem:
    """Universal configuration system - works with any MCP server."""

    def __init__(self):
        self.adapter = universal_adapter

    def adapt_config(
        self, config: Dict[str, Any], server_info: Any = None
    ) -> Dict[str, Any]:
        """Universal config adaptation for any MCP server."""
        return self.adapter.adapt_config(config, server_info)

    def cleanup(self):
        """No cleanup needed for universal system."""
        pass
