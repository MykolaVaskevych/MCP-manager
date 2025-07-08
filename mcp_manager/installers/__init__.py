"""MCP server installers."""

from pathlib import Path

from .universal import BaseInstaller, UniversalInstaller

# Global universal installer instance
_universal_installer = None


def get_installer(source: str, base_install_dir: Path = None) -> BaseInstaller:
    """Get appropriate installer for source."""
    global _universal_installer

    if base_install_dir is None:
        base_install_dir = Path.cwd() / "mcp-servers"

    if _universal_installer is None:
        _universal_installer = UniversalInstaller(base_install_dir)

    return _universal_installer.get_installer(source)


def get_universal_installer(base_install_dir: Path = None) -> UniversalInstaller:
    """Get the universal installer instance."""
    if base_install_dir is None:
        base_install_dir = Path.cwd() / "mcp-servers"

    return UniversalInstaller(base_install_dir)


__all__ = [
    "BaseInstaller",
    "UniversalInstaller",
    "get_installer",
    "get_universal_installer",
]
