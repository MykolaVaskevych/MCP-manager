"""Client identification system."""

import fnmatch
import logging
from datetime import datetime
from typing import Dict, List, Optional

import mcp.types as types

from ..config.models import MCPManagerConfig

logger = logging.getLogger(__name__)


class ConnectionContext:
    """Context information about a client connection."""

    def __init__(self):
        self.client_info: Optional[types.Implementation] = None
        self.transport_type: str = ""
        self.headers: Dict[str, str] = {}
        self.remote_address: str = ""
        self.timestamp: datetime = datetime.now()
        self.client_id: Optional[str] = None  # Set by identifier


class ClientIdentifier:
    """Identifies clients based on connection context."""

    def __init__(self, config: MCPManagerConfig):
        self.client_rules = config.clients

    async def identify_client(self, context: ConnectionContext) -> str:
        """Identify client based on connection context and return client ID."""

        for client_id, rule in self.client_rules.items():
            if await self._matches_rule(context, rule.identify_by):
                logger.info(f"Client identified as: {client_id}")
                context.client_id = client_id
                return client_id

        logger.info("Client not identified, using default")
        context.client_id = "default"
        return "default"

    async def _matches_rule(
        self, context: ConnectionContext, conditions: List[Dict]
    ) -> bool:
        """Check if connection context matches identification conditions."""
        for condition in conditions:
            for key, expected_value in condition.items():
                actual_value = self._extract_context_value(context, key)

                if not self._matches_value(actual_value, expected_value):
                    return False

        return True

    def _matches_value(self, actual: str, expected: str) -> bool:
        """Check if actual value matches expected (with wildcard support)."""
        if expected.endswith("*"):
            # Wildcard matching
            return fnmatch.fnmatch(actual, expected)
        else:
            # Exact matching
            return actual == expected

    def _extract_context_value(self, context: ConnectionContext, key: str) -> str:
        """Extract value from connection context based on key path."""
        try:
            if key == "client_info.name":
                if context.client_info:
                    # Try multiple possible structures
                    if (
                        hasattr(context.client_info, "clientInfo")
                        and context.client_info.clientInfo
                    ):
                        if hasattr(context.client_info.clientInfo, "name"):
                            return str(context.client_info.clientInfo.name)
                    # Fallback to direct name attribute
                    elif hasattr(context.client_info, "name"):
                        return str(context.client_info.name)
                return ""

            elif key == "client_info.version":
                if context.client_info:
                    # Try multiple possible structures
                    if (
                        hasattr(context.client_info, "clientInfo")
                        and context.client_info.clientInfo
                    ):
                        if hasattr(context.client_info.clientInfo, "version"):
                            return str(context.client_info.clientInfo.version)
                    # Fallback to direct version attribute
                    elif hasattr(context.client_info, "version"):
                        return str(context.client_info.version)
                return ""

            elif key == "connection_source" or key == "transport_type":
                return context.transport_type or ""

            elif key == "user_agent":
                if hasattr(context, "headers") and context.headers:
                    return context.headers.get("User-Agent", "")
                return ""

            elif key == "remote_address":
                return getattr(context, "remote_address", "")

            elif key.startswith("header."):
                # Extract specific header
                header_name = key[7:]  # Remove "header." prefix
                if hasattr(context, "headers") and context.headers:
                    return context.headers.get(header_name, "")
                return ""

            else:
                # Unknown key - provide graceful fallback
                logger.debug(f"Unknown context key: {key}")
                return ""

        except Exception as e:
            logger.debug(f"Error extracting context value for key '{key}': {e}")
            return ""
