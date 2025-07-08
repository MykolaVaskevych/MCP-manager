"""Main CLI interface for MCP Manager."""

import asyncio
import logging
from typing import Optional

import typer
from rich import print as rich_print
from rich.console import Console
from rich.table import Table

from ..config.manager import ConfigManager
from ..core.manager import MCPManager

app = typer.Typer(help="MCP Manager - Centralized MCP server management and routing")
console = Console()

# Global state
current_manager: Optional[MCPManager] = None


@app.command()
def start(
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as daemon"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging"
    ),
):
    """Start the MCP manager."""
    setup_logging(verbose)
    if daemon:
        rich_print(
            "[yellow]Daemon mode not yet implemented, running in foreground[/yellow]"
        )
    try:
        asyncio.run(start_manager(config))
    except KeyboardInterrupt:
        rich_print("\n[yellow]Shutting down MCP manager...[/yellow]")
    except Exception as e:
        rich_print(f"[red]Error starting MCP manager: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stop():
    """Stop the MCP manager."""
    rich_print("[yellow]Stop command not yet implemented[/yellow]")
    # This would communicate with a running daemon process


@app.command()
def status(
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
):
    """Show status of MCP manager and all servers."""
    try:
        asyncio.run(show_status(config))
    except Exception as e:
        rich_print(f"[red]Error getting status: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def reload(
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
):
    """Reload configuration without stopping manager."""
    rich_print("[yellow]Reload command not yet implemented[/yellow]")


# Server management commands
server_app = typer.Typer(help="Server management commands")
app.add_typer(server_app, name="server")


@server_app.command("list")
def list_servers(
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
):
    """List all configured servers."""
    try:
        asyncio.run(list_all_servers(config))
    except Exception as e:
        rich_print(f"[red]Error listing servers: {e}[/red]")
        raise typer.Exit(1)


@server_app.command("install")
def install_server(
    server_id: str = typer.Argument(..., help="Server ID to install"),
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
):
    """Install specific server."""
    try:
        asyncio.run(install_specific_server(config, server_id))
    except Exception as e:
        rich_print(f"[red]Error installing server: {e}[/red]")
        raise typer.Exit(1)


@server_app.command("start")
def start_server(
    server_id: str = typer.Argument(..., help="Server ID to start"),
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
):
    """Start specific server."""
    rich_print(
        f"[yellow]Start server command not yet implemented: {server_id}[/yellow]"
    )


@server_app.command("stop")
def stop_server(
    server_id: str = typer.Argument(..., help="Server ID to stop"),
):
    """Stop specific server."""
    rich_print(f"[yellow]Stop server command not yet implemented: {server_id}[/yellow]")


@server_app.command("restart")
def restart_server(
    server_id: str = typer.Argument(..., help="Server ID to restart"),
):
    """Restart specific server."""
    rich_print(
        f"[yellow]Restart server command not yet implemented: {server_id}[/yellow]"
    )


@server_app.command("logs")
def show_logs(
    server_id: str = typer.Argument(..., help="Server ID"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
):
    """Show server logs."""
    rich_print(f"[yellow]Logs command not yet implemented: {server_id}[/yellow]")


# Configuration management commands
config_app = typer.Typer(help="Configuration management commands")
app.add_typer(config_app, name="config")


@config_app.command("validate")
def validate_config(
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
):
    """Validate configuration file."""
    try:
        config_manager = ConfigManager(config)
        issues = config_manager.validate_config()

        if not issues:
            rich_print("[green]Configuration is valid![/green]")
        else:
            rich_print("[red]Configuration validation failed:[/red]")
            for issue in issues:
                rich_print(f"  [red]•[/red] {issue}")
            raise typer.Exit(1)

    except Exception as e:
        rich_print(f"[red]Error validating configuration: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("show")
def show_config(
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
):
    """Show current configuration."""
    try:
        config_manager = ConfigManager(config)
        config_obj = config_manager.load_config()

        # Display configuration in a nice format
        rich_print("[bold]MCP Manager Configuration[/bold]")
        rich_print(f"Manager: {config_obj.manager.name} v{config_obj.manager.version}")

        if config_obj.servers:
            rich_print(f"\n[bold]Servers ({len(config_obj.servers)}):[/bold]")
            for server_id, server_config in config_obj.servers.items():
                status = (
                    "[green]enabled[/green]"
                    if server_config.enabled
                    else "[red]disabled[/red]"
                )
                rich_print(f"  • {server_id}: {server_config.source} ({status})")

        if config_obj.clients:
            rich_print(f"\n[bold]Clients ({len(config_obj.clients)}):[/bold]")
            for client_id in config_obj.clients.keys():
                rich_print(f"  • {client_id}")

    except Exception as e:
        rich_print(f"[red]Error showing configuration: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("edit")
def edit_config(
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
):
    """Edit configuration file."""
    import os

    editor = os.environ.get("EDITOR", "nano")
    os.system(f"{editor} {config}")


# Client management commands
client_app = typer.Typer(help="Client management commands")
app.add_typer(client_app, name="client")


@client_app.command("list")
def list_clients():
    """List active client connections."""
    rich_print("[yellow]List clients command not yet implemented[/yellow]")


@client_app.command("permissions")
def show_permissions(
    client_id: str = typer.Argument(..., help="Client ID"),
    config: str = typer.Option(
        "mcp-manager.yaml", "--config", "-c", help="Configuration file path"
    ),
):
    """Show client permissions."""
    try:
        asyncio.run(show_client_permissions(client_id, config))
    except Exception as e:
        rich_print(f"[red]Error showing permissions: {e}[/red]")
        raise typer.Exit(1)


# Implementation functions
async def start_manager(config_path: str):
    """Start the MCP manager."""
    global current_manager

    rich_print(f"[blue]Starting MCP Manager with config: {config_path}[/blue]")

    try:
        current_manager = MCPManager(config_path)
        await current_manager.start()
    except Exception as e:
        rich_print(f"[red]Failed to start MCP manager: {e}[/red]")
        raise


async def show_status(config_path: str):
    """Show status of all servers."""
    config_manager = ConfigManager(config_path)
    config = config_manager.load_config()

    # Create a table for server status
    table = Table(title="MCP Server Status")
    table.add_column("Server ID", style="cyan")
    table.add_column("Source", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Transport", style="yellow")
    table.add_column("Enabled", style="blue")

    for server_id, server_config in config.servers.items():
        status = "Not Running"  # Would check actual status
        enabled = "✓" if server_config.enabled else "✗"

        table.add_row(
            server_id, server_config.source, status, server_config.transport, enabled
        )

    console.print(table)


async def list_all_servers(config_path: str):
    """List all configured servers."""
    config_manager = ConfigManager(config_path)
    config = config_manager.load_config()

    if not config.servers:
        rich_print("[yellow]No servers configured[/yellow]")
        return

    # Create a table for servers
    table = Table(title="Configured MCP Servers")
    table.add_column("Server ID", style="cyan")
    table.add_column("Source", style="magenta")
    table.add_column("Version", style="yellow")
    table.add_column("Transport", style="blue")
    table.add_column("Auto Install", style="green")
    table.add_column("Enabled", style="red")

    for server_id, server_config in config.servers.items():
        version = server_config.version or "latest"
        auto_install = "✓" if server_config.auto_install else "✗"
        enabled = "✓" if server_config.enabled else "✗"

        table.add_row(
            server_id,
            server_config.source,
            version,
            server_config.transport,
            auto_install,
            enabled,
        )

    console.print(table)


async def install_specific_server(config_path: str, server_id: str):
    """Install a specific server."""
    rich_print(f"[blue]Installing server: {server_id}[/blue]")

    config_manager = ConfigManager(config_path)
    config = config_manager.load_config()

    if server_id not in config.servers:
        rich_print(f"[red]Server {server_id} not found in configuration[/red]")
        return

    # This would use the installer system
    rich_print(f"[green]Server {server_id} would be installed here[/green]")


async def show_client_permissions(client_id: str, config_path: str):
    """Show permissions for a specific client."""
    config_manager = ConfigManager(config_path)
    config = config_manager.load_config()

    if client_id not in config.clients:
        rich_print(f"[red]Client {client_id} not found in configuration[/red]")
        return

    client_rule = config.clients[client_id]

    rich_print(f"[bold]Permissions for client: {client_id}[/bold]")

    # Show identification rules
    rich_print("\n[bold]Identification rules:[/bold]")
    for rule in client_rule.identify_by:
        for key, value in rule.items():
            rich_print(f"  • {key}: {value}")

    # Show allow rules
    if client_rule.allow:
        rich_print("\n[bold]Allow rules:[/bold]")
        for rule in client_rule.allow:
            tools = rule.tools or ["*"]
            rich_print(f"  • Server {rule.server}: tools={tools}")

    # Show deny rules
    if client_rule.deny:
        rich_print("\n[bold]Deny rules:[/bold]")
        for rule in client_rule.deny:
            tools = rule.tools or ["*"]
            rich_print(f"  • Server {rule.server}: tools={tools}")

    # Show default policy
    default_policy = (
        "deny all except allowed"
        if client_rule.deny_all_except_allowed
        else "allow all except denied"
    )
    rich_print(f"\n[bold]Default policy:[/bold] {default_policy}")


def setup_logging(verbose: bool):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def main():
    """Main entry point for CLI."""
    app()
