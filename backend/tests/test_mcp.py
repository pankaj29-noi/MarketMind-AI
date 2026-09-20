"""MCP client discovery tests — skip cleanly when optional adapters are absent."""
import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("langchain_mcp_adapters")
from langchain_mcp_adapters.client import MultiServerMCPClient


def test_mcp_tool_discovery():
    server_path = Path(__file__).resolve().parents[1] / "mcp_server" / "server.py"
    if not server_path.exists():
        pytest.skip("mcp_server/server.py not present")

    config = {
        "dataagent_tools": {
            "command": sys.executable,
            "args": [str(server_path)],
            "transport": "stdio",
        }
    }

    async def _run():
        client = MultiServerMCPClient(config)
        tools = await client.get_tools()
        return [t.name for t in tools]

    tool_names = asyncio.run(_run())
    assert "get_dataset_schema" in tool_names
