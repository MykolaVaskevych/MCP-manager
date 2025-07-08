"""Permission and access control engine."""

import logging
from typing import Dict, List

import mcp.types as types

from ..config.models import AccessRule, MCPManagerConfig

logger = logging.getLogger(__name__)


class PermissionEngine:
    """Manages permissions and access control for clients."""

    def __init__(self, config: MCPManagerConfig):
        self.client_rules = config.clients

    async def check_tool_access(
        self, client_id: str, server_id: str, tool_name: str
    ) -> bool:
        """Check if client has access to specific tool."""
        rule = self.client_rules.get(client_id)
        if not rule:
            # Try default rule
            rule = self.client_rules.get("default")
            if not rule:
                logger.warning(f"No access rules found for client: {client_id}")
                return False

        # Check explicit denies first (deny takes precedence)
        for deny_rule in rule.deny:
            if self._matches_access_rule(deny_rule, server_id, tool_name, "tools"):
                logger.debug(
                    f"Tool access denied by explicit rule: {client_id} -> {server_id}.{tool_name}"
                )
                return False

        # Check explicit allows
        for allow_rule in rule.allow:
            if self._matches_access_rule(allow_rule, server_id, tool_name, "tools"):
                logger.debug(
                    f"Tool access allowed by explicit rule: {client_id} -> {server_id}.{tool_name}"
                )
                return True

        # Default behavior based on rule configuration
        if rule.deny_all_except_allowed:
            logger.debug(
                f"Tool access denied by default policy: {client_id} -> {server_id}.{tool_name}"
            )
            return False
        else:
            logger.debug(
                f"Tool access allowed by default policy: {client_id} -> {server_id}.{tool_name}"
            )
            return True

    async def check_resource_access(
        self, client_id: str, server_id: str, resource_uri: str
    ) -> bool:
        """Check if client has access to specific resource."""
        rule = self.client_rules.get(client_id)
        if not rule:
            rule = self.client_rules.get("default")
            if not rule:
                return False

        # Extract resource name from URI for matching
        resource_name = self._extract_resource_name(resource_uri)

        # Check explicit denies first
        for deny_rule in rule.deny:
            if self._matches_access_rule(
                deny_rule, server_id, resource_name, "resources"
            ):
                return False

        # Check explicit allows
        for allow_rule in rule.allow:
            if self._matches_access_rule(
                allow_rule, server_id, resource_name, "resources"
            ):
                return True

        # Default behavior
        return not rule.deny_all_except_allowed

    def _matches_access_rule(
        self, rule: AccessRule, server_id: str, item_name: str, item_type: str
    ) -> bool:
        """Check if access rule matches server and tool/resource."""
        if rule.server != server_id:
            return False

        # Get the appropriate item list (tools or resources)
        if item_type == "tools":
            items = rule.tools
        elif item_type == "resources":
            items = rule.resources
        else:
            return False

        if not items:  # Empty list means all items
            return True

        # Check if item is in the list or if wildcard matches
        return (
            item_name in items or "*" in items or self._wildcard_match(item_name, items)
        )

    def _wildcard_match(self, item_name: str, patterns: List[str]) -> bool:
        """Check if item name matches any wildcard patterns."""
        import fnmatch

        for pattern in patterns:
            if fnmatch.fnmatch(item_name, pattern):
                return True
        return False

    def _extract_resource_name(self, resource_uri: str) -> str:
        """Extract resource name from URI for matching."""
        # Remove scheme and server prefix if present
        if "://" in resource_uri:
            _, path = resource_uri.split("://", 1)
            if "/" in path:
                _, resource_name = path.split("/", 1)
                return resource_name
            return path
        return resource_uri

    async def filter_tools(
        self, client_id: str, server_tools: Dict[str, List[types.Tool]]
    ) -> Dict[str, List[types.Tool]]:
        """Filter available tools based on client permissions."""
        filtered_tools = {}

        for server_id, tools in server_tools.items():
            allowed_tools = []

            for tool in tools:
                if await self.check_tool_access(client_id, server_id, tool.name):
                    allowed_tools.append(tool)

            if allowed_tools:
                filtered_tools[server_id] = allowed_tools

        return filtered_tools

    async def filter_resources(
        self, client_id: str, server_resources: Dict[str, List[types.Resource]]
    ) -> Dict[str, List[types.Resource]]:
        """Filter available resources based on client permissions."""
        filtered_resources = {}

        for server_id, resources in server_resources.items():
            allowed_resources = []

            for resource in resources:
                if await self.check_resource_access(client_id, server_id, resource.uri):
                    allowed_resources.append(resource)

            if allowed_resources:
                filtered_resources[server_id] = allowed_resources

        return filtered_resources

    def get_client_permissions(self, client_id: str) -> Dict:
        """Get permission summary for a client."""
        rule = self.client_rules.get(client_id)
        if not rule:
            return {"error": "Client not found"}

        return {
            "client_id": client_id,
            "identify_by": rule.identify_by,
            "allow_rules": [
                {
                    "server": r.server,
                    "tools": r.tools,
                    "resources": r.resources,
                }
                for r in rule.allow
            ],
            "deny_rules": [
                {
                    "server": r.server,
                    "tools": r.tools,
                    "resources": r.resources,
                }
                for r in rule.deny
            ],
            "deny_all_except_allowed": rule.deny_all_except_allowed,
        }
