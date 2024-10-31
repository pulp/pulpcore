import pytest

from aiohttp import web

from pulpcore.content.instrumentation import instrumentation


@pytest.fixture
def run_middleware(aiohttp_client):
    async def _run_middleware(provider):
        app = web.Application(middlewares=[instrumentation(provider=provider)])

        app.router.add_get("/", lambda req: web.Response())

        client = await aiohttp_client(app)

        await client.get("/")

    return _run_middleware


@pytest.mark.asyncio
async def test_instrumentation(meter_provider, run_middleware):
    await run_middleware(meter_provider)
