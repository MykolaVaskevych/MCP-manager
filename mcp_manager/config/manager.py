"""Configuration manager."""

import os
from pathlib import Path
from typing import Any, List, Optional

import yaml
from pydantic import ValidationError

from .models import ClientRule, MCPManagerConfig, ServerConfig


class ConfigManager:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config: Optional[MCPManagerConfig] = None

    def load_config(self) -> MCPManagerConfig:
        """Load and validate configuration."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        try:
            with open(self.config_path, "r") as f:
                config_data = yaml.safe_load(f)

            # Expand environment variables
            config_data = self._expand_env_vars(config_data)

            # Validate against schema
            self.config = MCPManagerConfig(**config_data)
            return self.config

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML syntax: {e}")
        except ValidationError as e:
            raise ValueError(f"Configuration validation failed: {e}")

    def validate_config(self) -> List[str]:
        """Validate configuration and return any issues."""
        issues = []

        try:
            config = self.load_config()

            # Check server sources exist and are valid
            for server_id, server_config in config.servers.items():
                if not self._validate_server_source(server_config):
                    issues.append(
                        f"Server {server_id}: invalid source {server_config.source}"
                    )

            # Check client rule conflicts
            for client_id, client_rule in config.clients.items():
                conflicts = self._check_rule_conflicts(client_rule)
                if conflicts:
                    issues.extend(
                        [f"Client {client_id}: {conflict}" for conflict in conflicts]
                    )

        except Exception as e:
            issues.append(f"Configuration error: {e}")

        return issues

    def _expand_env_vars(self, data: Any) -> Any:
        """Recursively expand environment variables in configuration."""
        if isinstance(data, dict):
            return {k: self._expand_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._expand_env_vars(item) for item in data]
        elif isinstance(data, str) and data.startswith("${") and data.endswith("}"):
            env_var = data[2:-1]
            return os.getenv(env_var, data)
        else:
            return data

    def _validate_server_source(self, server_config: ServerConfig) -> bool:
        """Validate server source format."""
        source = server_config.source

        if ":" not in source:
            return False

        source_type, source_path = source.split(":", 1)

        if source_type not in ["npm", "github", "local"]:
            return False

        if source_type == "local":
            # Check if local path exists
            if not Path(source_path).exists():
                return False

        return True

    def _check_rule_conflicts(self, client_rule: ClientRule) -> List[str]:
        """Check for conflicts in client access rules."""
        conflicts = []

        # Check for overlapping allow/deny rules
        allow_servers = {rule.server for rule in client_rule.allow}
        deny_servers = {rule.server for rule in client_rule.deny}

        overlapping = allow_servers & deny_servers
        if overlapping:
            conflicts.append(f"Overlapping allow/deny rules for servers: {overlapping}")

        return conflicts

    def get_config(self) -> MCPManagerConfig:
        """Get current configuration, loading if needed."""
        if self.config is None:
            self.load_config()
        return self.config

    def reload_config(self) -> MCPManagerConfig:
        """Force reload configuration from file."""
        self.config = None
        return self.load_config()

    def watch_config(self) -> bool:
        """Check if configuration file has been modified."""
        if not hasattr(self, "_last_modified"):
            self._last_modified = self.config_path.stat().st_mtime
            return False

        current_modified = self.config_path.stat().st_mtime
        if current_modified > self._last_modified:
            self._last_modified = current_modified
            return True

        return False
