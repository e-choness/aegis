import sys
from pathlib import Path
import pytest
import asyncio
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session", autouse=True)
def initialize_app_state():
    """Initialize app state for all tests by triggering lifespan."""
    from src.aegis.main import app, lifespan

    # Manually trigger lifespan setup for testing
    # This ensures app.state is properly initialized
    async def setup():
        async with lifespan(app):
            yield

    # Run the async setup in the event loop
    async_gen = setup()
    try:
        asyncio.run(async_gen.__anext__())
    except StopAsyncIteration:
        pass

    yield

    # Cleanup - exit the async context
    try:
        asyncio.run(async_gen.__anext__())
    except (StopAsyncIteration, RuntimeError):
        # RuntimeError may occur if event loop is already closed
        pass
