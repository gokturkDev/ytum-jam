import json

import httpx2
import openai
import pytest

from ambassador.adapters.openai import OpenAIEvaluator
from ambassador.application.errors import EvaluationError
from ambassador.domain.game import Game, Objection, Rules
from ambassador.ports.evaluator import FaceoffContext
from ambassador.scenarios.loader import default_scenario, load_personas


def context():
    personas = load_personas()
    game = Game(default_scenario(), Rules(), personas)
    game.current_objections = (Objection("r1-o1", "peter", "Peter Griffin", "Pastam nerede?"),)
    return FaceoffContext(game, personas[:1], "Pasta benden!")


def provider_body(status="completed", content=None):
    if content is None:
        content = [
            {
                "type": "output_text",
                "annotations": [],
                "text": json.dumps(
                    {
                        "objections": [{"persona_id": "peter", "text_tr": "Pastam nerede?"}],
                    }
                ),
            }
        ]
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "model": "test-structured-model",
        "status": status,
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": content,
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
    }


async def test_actual_sdk_parses_structured_response():
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert "temperature" not in body and "reasoning" not in body
        assert body["store"] is False
        assert body["max_output_tokens"] == 1200
        return httpx2.Response(200, json=provider_body())

    async with openai.AsyncOpenAI(
        api_key="test-placeholder",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    ) as client:
        result = await OpenAIEvaluator(client, "test-structured-model", 1200).generate(context())
    assert result.objections[0].persona_id == "peter"
    assert result.objections[0].text_tr == "Pastam nerede?"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "kind,code,retryable",
    [
        ("refusal", "PROVIDER_REFUSAL", False),
        ("incomplete", "PROVIDER_INCOMPLETE", True),
        ("incomplete_partial", "PROVIDER_INCOMPLETE", True),
        ("401", "PROVIDER_CONFIGURATION", False),
        ("400", "PROVIDER_CONFIGURATION", False),
        ("404", "PROVIDER_CONFIGURATION", False),
        ("408", "PROVIDER_UNAVAILABLE", True),
        ("409", "PROVIDER_UNAVAILABLE", True),
        ("429", "PROVIDER_UNAVAILABLE", True),
        ("500", "PROVIDER_UNAVAILABLE", True),
    ],
)
async def test_provider_failure_mapping_without_sdk_retry(kind, code, retryable):
    calls = []

    def handle(request):
        calls.append(request)
        if kind == "refusal":
            return httpx2.Response(
                200,
                json=provider_body(
                    content=[
                        {
                            "type": "refusal",
                            "refusal": "No.",
                        }
                    ]
                ),
            )
        if kind == "incomplete_partial":
            return httpx2.Response(
                200,
                json=provider_body(
                    status="incomplete",
                    content=[
                        {
                            "type": "output_text",
                            "annotations": [],
                            "text": '{"stance":',
                        }
                    ],
                ),
            )
        if kind == "incomplete":
            return httpx2.Response(200, json=provider_body(status="incomplete", content=[]))
        return httpx2.Response(int(kind), json={"error": {"message": "private provider details"}})

    async with openai.AsyncOpenAI(
        api_key="test-placeholder",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    ) as client:
        with pytest.raises(EvaluationError) as exc:
            await OpenAIEvaluator(client, "test-model", 1200).generate(context())
    assert exc.value.code == code
    assert exc.value.retryable == retryable
    assert "private" not in str(exc.value)
    assert len(calls) == 1


async def test_actual_sdk_parses_answer_quality():
    def handle(request):
        payload = json.loads(request.content)
        assert "current_untrusted_player_answer_tr" in payload["input"][0]["content"]
        return httpx2.Response(
            200,
            json=provider_body(
                content=[
                    {
                        "type": "output_text",
                        "annotations": [],
                        "text": json.dumps(
                            {
                                "assessments": [{"objection_id": "r1-o1", "quality": "answered"}],
                                "feedback_tr": "Pasta geldi, itiraz eridi!",
                            }
                        ),
                    }
                ]
            ),
        )

    async with openai.AsyncOpenAI(
        api_key="test-placeholder",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    ) as client:
        result = await OpenAIEvaluator(client, "test-model", 1200).evaluate(context())
    assert result.assessments[0].quality.value == "answered"
