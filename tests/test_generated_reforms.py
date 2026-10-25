import asyncio
from collections import Counter
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from ambassador.adapters.fake import FakeEvaluator
from ambassador.api.app import create_app
from ambassador.application.errors import EvaluationError
from ambassador.config import Settings


async def test_topic_to_finished_game_and_session_isolation():
    app = create_app(settings=Settings(_env_file=None, llm_backend="fake"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        catalog = (await client.get("/v2/scenarios")).json()
        games = []
        for _ in range(2):
            response = await client.post("/v2/games", json={"topic": "  Köylerde ortak fırın  "})
            assert response.status_code == 201, response.text
            games.append(response.json())
        game, other = games
        assert game["game_id"] != other["game_id"]
        assert game["scenario"]["id"] != other["scenario"]["id"]
        assert game["scenario"]["title_tr"] == "Köylerde ortak fırın"
        assert game["scenario"]["public_facts_tr"]
        assert game["scenario"]["visual_effect"] is None
        assert game["allowed_actions"] == ["submit_answer"]
        assert len(game["current_objections"]) == 1
        private = app.state.service.read(game["game_id"]).scenario
        assert private.facts_en
        assert {p for p, _ in private.objections_by_persona} == {
            p.id for p in app.state.service.personas
        }
        assert all(len(examples) == 3 for _, examples in private.objections_by_persona)
        path = f"/v2/games/{game['game_id']}"
        for version in range(game["total_rounds"]):
            answer = {
                "request_id": str(uuid4()),
                "expected_version": version,
                "text": "Fırını sırayla kullanıp masrafları paylaşabiliriz.",
            }
            result = await client.post(path + "/answers", json=answer)
            assert result.status_code == 200, result.text
            assert (await client.post(path + "/answers", json=answer)).json() == result.json()
        assert result.json()["game"]["phase"] == "finished"
        assert (await client.get(path)).json() == result.json()["game"]
        assert (await client.get(f"/v2/games/{other['game_id']}")).json() == other
        assert (await client.get("/v2/scenarios")).json() == catalog
        response = await client.post("/v2/games", json={"scenario_id": private.id})
        assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"topic": ""},
        {"topic": " \n\t "},
        {"topic": "x" * 501},
        {"topic": 123},
        {"topic": True},
        {"topic": None},
        {"topic": "Ortak fırın", "scenario_id": "toothbrushing_v1"},
        {"topic": "Ortak fırın", "rounds": 100},
    ],
)
async def test_invalid_topic_never_calls_provider(client, service, payload):
    class Never(FakeEvaluator):
        async def draft_reform(self, topic):
            pytest.fail("Invalid input called provider")

    service.reform_generator = Never()
    response = await client.post("/v2/games", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert service.repository.entries == {}


async def test_generated_rules_respect_server_overrides():
    app = create_app(
        settings=Settings(
            _env_file=None, llm_backend="fake", starting_support=0, target_support=10, max_rounds=1
        )
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v2/games", json={"topic": "Ortak fırın"})
        assert response.status_code == 201
        game = response.json()
        assert game["support_percent"] == 0
        assert game["target_percent"] == 10
        assert game["total_rounds"] == 1


@pytest.mark.parametrize("limit", [1, 2, 3])
async def test_parallel_sessions_share_provider_limit(client, service, limit):
    entered, release = asyncio.Queue(), asyncio.Event()

    class Tracked(FakeEvaluator):
        active = 0
        peak = 0

        async def generate_concerns(self, scenario, persona):
            self.active += 1
            self.peak = max(self.peak, self.active)
            entered.put_nowait(persona.id)
            try:
                await release.wait()
                return await super().generate_concerns(scenario, persona)
            finally:
                self.active -= 1

    generator = Tracked()
    service.reform_generator = generator
    service.semaphore = asyncio.Semaphore(limit)
    pending = [
        asyncio.create_task(client.post("/v2/games", json={"topic": topic}))
        for topic in ("Ortak fırın", "Köy kuyuları")
    ]
    try:
        async with asyncio.timeout(2):
            for _ in range(limit):
                await entered.get()
        assert generator.active == limit
        assert service.repository.entries == {}
    finally:
        release.set()
        responses = await asyncio.gather(*pending)
    assert all(response.status_code == 201 for response in responses)
    assert generator.peak == limit
    assert generator.active == 0


async def test_generation_shares_limit_with_existing_gameplay(client, service):
    game = (await client.post("/v2/games", json={"scenario_id": "toothbrushing_v1"})).json()
    entered, release, drafted = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Blocked(FakeEvaluator):
        async def evaluate(self, context):
            entered.set()
            await release.wait()
            return await super().evaluate(context)

        async def draft_reform(self, topic):
            drafted.set()
            return await super().draft_reform(topic)

    provider = Blocked()
    service.evaluator = service.reform_generator = provider
    service.semaphore = asyncio.Semaphore(1)
    answer = asyncio.create_task(
        client.post(
            f"/v2/games/{game['game_id']}/answers",
            json={"request_id": str(uuid4()), "expected_version": 0, "text": "Bir önerim var."},
        )
    )
    await asyncio.wait_for(entered.wait(), 2)
    generation = asyncio.create_task(client.post("/v2/games", json={"topic": "Ortak fırın"}))
    try:
        # Queue generation behind the already running answer on the same semaphore.
        async with asyncio.timeout(0.02):
            await drafted.wait()
    except TimeoutError:
        pass
    finally:
        assert not drafted.is_set()
        release.set()
        results = await asyncio.gather(answer, generation)
    assert [r.status_code for r in results] == [200, 201]
    assert drafted.is_set()


@pytest.mark.parametrize("failure", ["provider", "deadline", "cancel"])
async def test_failure_cancels_siblings_without_publishing(client, service, failure):
    all_entered = asyncio.Event()

    class Blocked(FakeEvaluator):
        active = 0
        calls = 0

        async def generate_concerns(self, scenario, persona):
            self.active += 1
            self.calls += 1
            if self.active == len(service.personas):
                all_entered.set()
            try:
                await all_entered.wait()
                if failure == "provider" and persona == service.personas[0]:
                    raise EvaluationError("PROVIDER_CONFIGURATION", False, 503)
                await asyncio.Event().wait()
            finally:
                self.active -= 1

    generator = Blocked()
    service.reform_generator = generator
    service.attempt_timeout = 10
    service.generation_timeout = 0.05 if failure == "deadline" else 10
    pending = asyncio.create_task(client.post("/v2/games", json={"topic": "Ortak fırın"}))
    await asyncio.wait_for(all_entered.wait(), 2)
    if failure == "cancel":
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        response = await asyncio.wait_for(pending, 2)
        assert response.status_code == (503 if failure == "provider" else 504)
        assert response.json()["error"]["code"] == (
            "PROVIDER_CONFIGURATION" if failure == "provider" else "GENERATION_TIMEOUT"
        )
    assert generator.active == 0
    assert generator.calls == len(service.personas)
    assert service.repository.entries == {}
    assert service.semaphore._value == 3


async def test_retries_only_failed_persona_and_skips_initial_generation(client, service):
    calls = Counter()

    class Flaky(FakeEvaluator):
        async def draft_reform(self, topic):
            calls["draft"] += 1
            return await super().draft_reform(topic)

        async def generate_concerns(self, scenario, persona):
            calls[persona.id] += 1
            if persona == service.personas[0] and calls[persona.id] == 1:
                raise EvaluationError("PROVIDER_UNAVAILABLE", True, 503)
            return await super().generate_concerns(scenario, persona)

        async def generate(self, context):
            pytest.fail("First faceoff must reuse generated concerns")

    service.evaluator = service.reform_generator = Flaky()
    response = await client.post("/v2/games", json={"topic": "Ortak fırın"})
    assert response.status_code == 201, response.text
    assert calls == {
        "draft": 1,
        **{p.id: 2 if i == 0 else 1 for i, p in enumerate(service.personas)},
    }


@pytest.mark.parametrize("stage", ["draft", "concerns"])
async def test_invalid_provider_output_never_publishes(client, service, stage):
    class Invalid(FakeEvaluator):
        async def draft_reform(self, topic):
            output = await super().draft_reform(topic)
            if stage == "draft":
                output.title_tr = " "
            return output

        async def generate_concerns(self, scenario, persona):
            output = await super().generate_concerns(scenario, persona)
            output.objections_tr = ["Invalid"]
            return output

    service.reform_generator = Invalid()
    response = await client.post("/v2/games", json={"topic": "Ortak fırın"})
    assert response.status_code == 502
    assert service.repository.entries == {}
