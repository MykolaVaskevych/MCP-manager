# MCP Manager

A centralized MCP (Model Context Protocol) server management and routing system
that allows you to manage multiple MCP servers through a single interface
with fine-grained access control.

## Features

- **Centralized Management**: Manage multiple MCP servers from a single configuration file
- **Access Control**: Fine-grained permissions per client with rule-based access control
- **Auto-Installation**: Automatic discovery and installation of MCP servers from NPM, GitHub, or local sources
- **Hot Reload**: Configuration changes without service restart
- **Health Monitoring**: Automatic health checks and server restart capabilities
- **Request Routing**: Intelligent routing of requests to appropriate backend servers
- **Response Caching**: Performance optimization with configurable TTL
- **CLI Management**: Comprehensive command-line interface for operations

## Quick Start

1. **Install dependencies**:

   ```bash
   cd MCP-manager
   pip install -e .
   ```

2. **Create configuration**:

   ```bash
   cp mcp-manager.example.yaml mcp-manager.yaml
   # Edit mcp-manager.yaml to configure your servers and access rules
   ```

3. **Start the manager**:

   ```bash
   python main.py mcp-manager.yaml
   # OR use the CLI
   mcp-manager start --config mcp-manager.yaml
   ```

4. **Connect your MCP clients** (VSCode, Claude Desktop, etc.) to the manager instead of individual servers.

## Configuration

The manager uses a YAML configuration file that defines:

- **Servers**: MCP servers to manage (NPM packages, GitHub repos, local paths)
- **Clients**: Access rules for different clients (VSCode, Claude Desktop, etc.)
- **Sources**: Installation sources (NPM registry, GitHub API, local paths)
- **Runtime**: Performance and operational settings

### Example Configuration

```yaml
manager:
  name: "central-mcp-manager"
  log_level: "info"

servers:
  weather:
    source: "npm:@weather/mcp-weather"
    transport: "stdio"
    auto_install: true
    
  filesystem:
    source: "github:anthropics/mcp-filesystem"
    transport: "stdio"
    config:
      allowed_paths: ["/home/user/documents"]

clients:
  vscode:
    identify_by:
      - client_info.name: "vscode-mcp"
    allow:
      - server: "filesystem"
        tools: ["read_file", "write_file"]
    deny:
      - server: "weather"
      
  claude_desktop:
    identify_by:
      - client_info.name: "claude-desktop"
    allow:
      - server: "weather"
        tools: ["get_weather"]
      - server: "filesystem" 
        tools: ["read_file"]  # Read-only
```

## Client Integration

### VSCode MCP Extension

```json
{
  "mcp.servers": {
    "manager": {
      "command": "python",
      "args": ["/path/to/MCP-manager/main.py", "/path/to/mcp-manager.yaml"],
      "transport": "stdio"
    }
  }
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "manager": {
      "command": "python",
      "args": ["/path/to/MCP-manager/main.py", "/path/to/mcp-manager.yaml"],
      "transport": "stdio"
    }
  }
}
```

## CLI Commands

```bash
# Start the manager
mcp-manager start --config mcp-manager.yaml

# Check status
mcp-manager status

# List configured servers  
mcp-manager server list

# Install a server
mcp-manager server install weather

# Show client permissions
mcp-manager client permissions vscode

# Validate configuration
mcp-manager config validate

# View current config
mcp-manager config show
```

## Architecture

```
[MCP Client] <---> [MCP Manager] <---> [MCP Server 1]
                         |
                         +-----------> [MCP Server 2]
                         |  
                         +-----------> [MCP Server N]
```

The MCP Manager acts as both:

- **MCP Server**: Exposes tools/resources to clients
- **MCP Client**: Connects to backend MCP servers

Key components:

- **Server Manager**: Handles backend server lifecycle
- **Access Control**: Client identification and permission enforcement  
- **Router**: Request routing and response aggregation
- **Cache**: Response caching for performance
- **Installers**: Automatic server installation from various sources

## Supported Server Sources

- **NPM**: `npm:package-name` or `npm:@scope/package-name`
- **GitHub**: `github:owner/repo` with optional branch
- **Local**: `local:/path/to/server` or `local:./relative/path`

## Access Control

The manager supports sophisticated access control:

- **Client Identification**: Based on client info, transport type, headers
- **Rule-based Permissions**: Allow/deny rules for servers, tools, resources
- **Wildcard Matching**: Support for pattern-based matching
- **Default Policies**: Configurable fallback behavior

## Development

Project structure:

```
mcp_manager/
├── config/          # Configuration management
├── server/          # MCP server management  
├── access/          # Access control system
├── routing/         # Request routing engine
├── installers/      # Server installation
├── cli/             # Command line interface
└── core/            # Main application
```

## Environment Variables

- `WEATHER_API_KEY`: API key for weather services
- `DATABASE_URL`: Database connection string
- `NPM_TOKEN`: NPM authentication token (optional)
- `GITHUB_TOKEN`: GitHub authentication token (optional)

## Troubleshooting

1. **Server won't start**: Check configuration with `mcp-manager config validate`
2. **Access denied**: Review client permissions with `mcp-manager client permissions <client_id>`
3. **Installation fails**: Ensure source URLs are correct and tokens are set
4. **Performance issues**: Check cache settings and concurrent request limits

## License

MIT License - see LICENSE file for details.

