"""Response aggregation for multiple MCP servers."""

import asyncio
import logging
from typing import List

import mcp.types as types

from ..server.manager import MCPServerManager

logger = logging.getLogger(__name__)


class ResponseAggregator:
    """Aggregates responses from multiple MCP servers."""

    def __init__(self, server_manager: MCPServerManager):
        self.server_manager = server_manager

    async def aggregate_tools(self, client_id: str) -> List[types.Tool]:
        """Aggregate tools from all available backend servers."""
        all_tools = []

        # Get all active backend sessions
        backend_sessions = self.server_manager.get_active_sessions()

        if not backend_sessions:
            logger.warning("No active backend sessions for tool aggregation")
            return all_tools

        # Collect tools from all backends concurrently
        tasks = []
        for server_id, process in backend_sessions.items():
            task = asyncio.create_task(
                self._get_server_tools(server_id, process),
                name=f"get_tools_{server_id}",
            )
            tasks.append(task)

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for server_id, result in zip(backend_sessions.keys(), results):
            if isinstance(result, Exception):
                # Log error but continue with other servers
                logger.warning(f"Failed to get tools from {server_id}: {result}")
                continue

            if isinstance(result, types.ListToolsResult):
                # Namespace tools with server ID
                for tool in result.tools:
                    namespaced_tool = types.Tool(
                        name=f"{server_id}.{tool.name}",
                        description=f"[{server_id}] {tool.description}",
                        inputSchema=tool.inputSchema,
                    )
                    all_tools.append(namespaced_tool)

        logger.info(
            f"Aggregated {len(all_tools)} tools from {len(backend_sessions)} servers"
        )
        return all_tools

    async def _get_server_tools(self, server_id: str, process) -> types.ListToolsResult:
        """Get tools from a specific backend server with timeout."""
        try:
            return await asyncio.wait_for(process.list_tools(), timeout=10.0)
        except asyncio.TimeoutError:
            raise Exception(f"Timeout getting tools from {server_id}")
        except Exception as e:
            raise Exception(f"Error getting tools from {server_id}: {e}")

    async def aggregate_resources(self, client_id: str) -> List[types.Resource]:
        """Aggregate resources from all available backend servers."""
        all_resources = []

        backend_sessions = self.server_manager.get_active_sessions()

        if not backend_sessions:
            logger.warning("No active backend sessions for resource aggregation")
            return all_resources

        # Similar pattern to tools aggregation
        tasks = []
        for server_id, process in backend_sessions.items():
            task = asyncio.create_task(
                self._get_server_resources(server_id, process),
                name=f"get_resources_{server_id}",
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for server_id, result in zip(backend_sessions.keys(), results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to get resources from {server_id}: {result}")
                continue

            if isinstance(result, types.ListResourcesResult):
                for resource in result.resources:
                    namespaced_resource = types.Resource(
                        uri=f"mcp://{server_id}/{resource.uri}",
                        name=f"{server_id}.{resource.name}" if resource.name else None,
                        description=f"[{server_id}] {resource.description}"
                        if resource.description
                        else None,
                        mimeType=resource.mimeType,
                    )
                    all_resources.append(namespaced_resource)

        logger.info(
            f"Aggregated {len(all_resources)} resources from {len(backend_sessions)} servers"
        )
        return all_resources

    async def _get_server_resources(
        self, server_id: str, process
    ) -> types.ListResourcesResult:
        """Get resources from a specific backend server with timeout."""
        try:
            return await asyncio.wait_for(process.list_resources(), timeout=10.0)
        except asyncio.TimeoutError:
            raise Exception(f"Timeout getting resources from {server_id}")
        except Exception as e:
            raise Exception(f"Error getting resources from {server_id}: {e}")

    async def aggregate_prompts(self, client_id: str) -> List[types.Prompt]:
        """Aggregate prompts from all available backend servers."""
        all_prompts = []

        backend_sessions = self.server_manager.get_active_sessions()

        if not backend_sessions:
            return all_prompts

        # Get prompts from all backends concurrently
        tasks = []
        for server_id, process in backend_sessions.items():
            task = asyncio.create_task(
                self._get_server_prompts(server_id, process),
                name=f"get_prompts_{server_id}",
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for server_id, result in zip(backend_sessions.keys(), results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to get prompts from {server_id}: {result}")
                continue

            if isinstance(result, types.ListPromptsResult):
                for prompt in result.prompts:
                    namespaced_prompt = types.Prompt(
                        name=f"{server_id}.{prompt.name}",
                        description=f"[{server_id}] {prompt.description}"
                        if prompt.description
                        else None,
                        arguments=prompt.arguments,
                    )
                    all_prompts.append(namespaced_prompt)

        logger.info(
            f"Aggregated {len(all_prompts)} prompts from {len(backend_sessions)} servers"
        )
        return all_prompts

    async def _get_server_prompts(
        self, server_id: str, process
    ) -> types.ListPromptsResult:
        """Get prompts from a specific backend server with timeout."""
        try:
            # Note: This assumes the process has a list_prompts method
            # Some MCP servers might not support prompts
            if hasattr(process, "list_prompts"):
                return await asyncio.wait_for(process.list_prompts(), timeout=10.0)
            else:
                # Return empty result if prompts not supported
                return types.ListPromptsResult(prompts=[])
        except asyncio.TimeoutError:
            raise Exception(f"Timeout getting prompts from {server_id}")
        except Exception as e:
            # If prompts not supported, return empty result
            if "not supported" in str(e).lower():
                return types.ListPromptsResult(prompts=[])
            raise Exception(f"Error getting prompts from {server_id}: {e}")
