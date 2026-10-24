import random

import pytest
from httpx import ASGITransport, AsyncClient

from ambassador.adapters.fake import FakeEvaluator
from ambassador.adapters.memory import MemoryRepository
from ambassador.api.app import create_app
from ambassador.application.service import GameService
from ambassador.config import Settings
from ambassador.scenarios.loader import default_scenario, load_personas


@pytest.fixture
def service():
    return GameService(
        MemoryRepository(),
        FakeEvaluator(),
        default_scenario(),
        load_personas(),
        rng=random.Random(7),
    )


@pytest.fixture
async def client(service):
    app = create_app(service, Settings(_env_file=None, llm_backend="fake"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
