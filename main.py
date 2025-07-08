#!/usr/bin/env python3
"""Main entry point for MCP Manager when run as a script."""

import asyncio
import sys
from pathlib import Path

# Add the package to Python path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_manager.core.manager import MCPManager


async def main():
    """Main entry point."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "mcp-manager.yaml"

    try:
        manager = MCPManager(config_path)
        await manager.start()
    except KeyboardInterrupt:
        print("\nShutting down MCP Manager...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
