import asyncio
from uuid import uuid4

import pytest

from ambassador.adapters.fake import FakeEvaluator
from ambassador.domain.game import Quality


def body(version, text="Pasta ve halay benden!"):
    return {"request_id": str(uuid4()), "expected_version": version, "text": text}


async def create(client):
    response = await client.post("/v2/games", json={"scenario_id": "toothbrushing_v1"})
    assert response.status_code == 201, response.text
    return response.json()


async def test_http_faceoff_complete_and_replay(client):
    assert (await client.get("/health")).json() == {
        "status": "ok",
        "backend": "fake",
        "configured": True,
    }
    game = await create(client)
    path = f"/v2/games/{game['game_id']}"
    assert game["version"] == 0 and game["support_percent"] == 30
    assert game["target_percent"] == 60 and game["total_rounds"] == 3
    assert game["round_number"] == 1 and game["outcome"] is None
    assert 1 <= len(game["current_objections"]) <= 3
    assert game["allowed_actions"] == ["submit_answer"]
    assert game["history"] == []
    assert (await client.get(path)).json() == game
    for obsolete in ("jury", "tally", "fondness", "reaction_history"):
        assert obsolete not in game
    for private in ("personality", "interests", "objection_examples_tr"):
        assert private not in str(game)
    first_body = body(0, "  Çeyrek altın ve protein benden!\n")
    first = (await client.post(path + "/answers", json=first_body)).json()
    assert first["round"]["answer"] == first_body["text"]
    assert first["round"]["support_delta"] == 10
    assert first["round"]["objections"] == game["current_objections"]
    assert first["game"]["round_number"] == 2
    second = (await client.post(path + "/answers", json=body(1))).json()
    assert second["game"]["support_percent"] == 60
    assert second["game"]["outcome"] is None
    third = (await client.post(path + "/answers", json=body(2))).json()
    final = third["game"]
    assert final["phase"] == "finished" and final["support_percent"] == 50
    assert final["outcome"]["won"] is False
    assert final["current_objections"] == [] and final["round_number"] is None
    assert final["allowed_actions"] == [] and len(final["history"]) == 3
    assert (await client.post(path + "/answers", json=first_body)).json() == first
    assert (await client.get(path)).json() == final
    assert (await client.post(path + "/answers", json=body(3))).status_code == 409
    changed = {**first_body, "text": "Farklı cevap"}
    assert (await client.post(path + "/answers", json=changed)).json()["error"]["code"] == (
        "REQUEST_ID_CONFLICT"
    )


@pytest.mark.parametrize(
    "quality,expected,won",
    [
        (Quality.PARTIAL, 60, True),
        (Quality.MISSED, 0, False),
        (Quality.ANSWERED, 90, True),
    ],
)
async def test_threshold_and_both_endings(client, service, quality, expected, won):
    class Fixed(FakeEvaluator):
        async def evaluate(self, context):
            decision = await super().evaluate(context)
            for a in decision.assessments:
                a.quality = quality
            return decision

    service.evaluator = Fixed()
    game = await create(client)
    for v in range(3):
        response = await client.post(f"/v2/games/{game['game_id']}/answers", json=body(v))
        assert response.status_code == 200
    outcome = response.json()["game"]["outcome"]
    assert outcome["support_percent"] == expected and outcome["won"] is won


@pytest.mark.parametrize(
    "update",
    [
        {"text": " \n "},
        {"text": "x" * 6001},
        {"text": 3},
        {"text": None},
        {"expected_version": -1},
        {"expected_version": True},
        {"expected_version": "0"},
        {"request_id": "invalid"},
        {"support_percent": 100},
        {"quality": "answered"},
    ],
)
async def test_invalid_input_no_provider_calls(client, service, update):
    game = await create(client)

    class Never(FakeEvaluator):
        async def evaluate(self, context):
            pytest.fail("Invalid request called provider")

    service.evaluator = Never()
    response = await client.post(f"/v2/games/{game['game_id']}/answers", json={**body(0), **update})
    assert response.status_code == 422
    assert response.json()["api_version"] == "2"
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert service.read(game["game_id"]).version == 0


async def test_unknown_stale_and_removed_routes(client):
    assert (await client.get(f"/v2/games/{uuid4()}")).status_code == 404
    assert (await client.get("/v2/games/not-a-uuid")).status_code == 422
    assert (await client.post("/v1/games", json={})).status_code == 404
    game = await create(client)
    path = f"/v2/games/{game['game_id']}"
    assert (await client.post(path + "/answers", json=body(0))).status_code == 200
    response = await client.post(path + "/answers", json=body(0))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_VERSION"


async def test_busy_over_http(client, service):
    game = await create(client)
    entered, release = asyncio.Event(), asyncio.Event()

    class Blocked(FakeEvaluator):
        async def evaluate(self, context):
            entered.set()
            await release.wait()
            return await super().evaluate(context)

    service.evaluator = Blocked()
    path = f"/v2/games/{game['game_id']}"
    command = body(0)
    pending = asyncio.create_task(client.post(path + "/answers", json=command))
    await entered.wait()
    assert (await client.get(path)).json() == game
    response = await client.post(path + "/answers", json=command)
    assert response.status_code == 409 and response.json()["error"]["code"] == "GAME_BUSY"
    release.set()
    first = await pending
    assert first.status_code == 200
    assert (await client.post(path + "/answers", json=command)).json() == first.json()


async def test_reform_catalog_and_effects_are_awarded_only_on_victory():
    from httpx import ASGITransport, AsyncClient

    from ambassador.api.app import create_app
    from ambassador.config import Settings

    for starting_support, won in ((50, True), (0, False)):
        app = create_app(
            settings=Settings(
                _env_file=None,
                llm_backend="fake",
                starting_support=starting_support,
                max_rounds=1,
            )
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            topics = (await http.get("/v2/scenarios")).json()
            assert len(topics) == 9
            assert len({topic["id"] for topic in topics}) == 9
            assert sum(topic["visual_effect"] is not None for topic in topics) == 5
            for topic in topics:
                response = await http.post("/v2/games", json={"scenario_id": topic["id"]})
                assert response.status_code == 201
                game = response.json()
                assert len(game["current_objections"]) == 1
                assert game["outcome"] is None
                final = await http.post(f"/v2/games/{game['game_id']}/answers", json=body(0))
                assert final.status_code == 200
                outcome = final.json()["game"]["outcome"]
                assert outcome["won"] is won
                assert bool(outcome["visual_effects"]) == (
                    won and topic["visual_effect"] is not None
                )
                if won and topic["id"] == "surnames_v1":
                    updates = outcome["visual_effects"][0]["name_updates"]
                    assert [p["name_tr"] for p in updates] == [
                        "Ayşe Demir",
                        "Hasan Yılmaz",
                        "Cem Kaya",
                    ]
            unknown = await http.post("/v2/games", json={"scenario_id": "marriage_v1"})
            assert unknown.status_code == 422
