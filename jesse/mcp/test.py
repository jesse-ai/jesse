import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def test_streamable_connection():
    async with streamable_http_client("http://127.0.0.1:9002/mcp") as (read, write, _):
        session = ClientSession(read, write)
        await session.initialize()

        tools = await session.list_tools()
        print("Tools:", [t.name for t in tools])

if __name__ == "__main__":
    asyncio.run(test_streamable_connection())