"""
Manual connectivity check for a running Jesse MCP server.

Reads the endpoint from JESSE_MCP_URL (default: the local dashboard origin) and the
dashboard token from JESSE_MCP_TOKEN, so the token never appears in the command line.
"""

import asyncio
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def test_streamable_connection():
    url = os.environ.get('JESSE_MCP_URL', 'http://localhost:9000/mcp')
    token = os.environ.get('JESSE_MCP_TOKEN')
    if not token:
        raise SystemExit('Set JESSE_MCP_TOKEN to your dashboard token (see docs/mcp/setup).')
    headers = {'Authorization': f'Bearer {token}'}
    async with httpx.AsyncClient(headers=headers, timeout=30) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                print("Tools:", [t.name for t in tools.tools])

if __name__ == "__main__":
    asyncio.run(test_streamable_connection())
