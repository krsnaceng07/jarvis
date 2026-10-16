import asyncio
from src.web_fetch_tool import web_fetch_tool, WebFetchArgs


class MockContext:
    pass


async def main():
    ctx = MockContext()
    args = WebFetchArgs(url="https://example.com")
    res = await web_fetch_tool.execute(ctx, args)
    print("SUCCESS:")
    print(res)


asyncio.run(main())
