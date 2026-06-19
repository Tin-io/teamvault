"""End-to-end MCP stdio test.

Spawns the TeamVault MCP server as a subprocess (the way Claude Code launches it),
opens an MCP client session over stdio, calls each tool. Verifies the MCP transport
works without needing the real Claude Code host.

Requires: sidecar running on $TEAMVAULT_PORT (default 18100), pointed at the sandbox space.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


async def main() -> int:
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.client.session import ClientSession

    repo = Path(__file__).resolve().parent.parent  # repo root
    venv_py = repo / ".venv" / "bin" / "python"

    params = StdioServerParameters(
        command=str(venv_py),
        args=["-m", "sidecar.mcp_server"],
        env={
            **os.environ,
            "TEAMVAULT_SIDECAR_URL": "http://localhost:18100",
            "TEAMVAULT_SPACE": "teamvault-template",
            "PYTHONPATH": str(repo),
        },
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. List tools
            tools_result = await session.list_tools()
            names = [t.name for t in tools_result.tools]
            print(f"[1] tools: {names}")
            assert "vault_search" in names, "vault_search missing"
            assert "vault_publish" in names, "vault_publish missing"
            assert "vault_status" in names, "vault_status missing"

            # 2. Call vault_status
            status_res = await session.call_tool("vault_status", {})
            status_text = status_res.content[0].text if status_res.content else ""
            print(f"[2] vault_status preview: {status_text[:150]}")
            assert "status" in status_text, "vault_status didn't return health JSON"

            # 3. Call vault_search
            search_res = await session.call_tool("vault_search", {"query": "MRN policy", "top_k": 2})
            search_text = search_res.content[0].text if search_res.content else ""
            print(f"[3] vault_search returned {len(search_text)} chars")
            assert "MRN" in search_text or "results" in search_text, "vault_search returned no MRN hit"

            # 4. Call vault_publish — write a transient entry through MCP
            publish_res = await session.call_tool(
                "vault_publish",
                {"slug": "mcp-e2e-marker", "content": "# MCP e2e marker\n\nWritten through MCP at " + str(asyncio.get_event_loop().time()), "tags": ["mcp", "e2e"]},
            )
            publish_text = publish_res.content[0].text if publish_res.content else ""
            print(f"[4] vault_publish preview: {publish_text[:200]}")
            assert "kb/entries" in publish_text or "error" in publish_text, "vault_publish didn't return path or error"

    print("[PASS] MCP stdio transport works end-to-end")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
