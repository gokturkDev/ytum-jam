import json
import logging
from dataclasses import asdict
from importlib.resources import files
from typing import TypeVar

import openai
from pydantic import BaseModel, ValidationError

from ambassador.application.errors import EvaluationError
from ambassador.ports.evaluator import AnswerDecision, FaceoffContext, ObjectionBatch

logger = logging.getLogger(__name__)
PROMPT_VERSION = "reforms-v3.0"
M = TypeVar("M", bound=BaseModel)


def build_prompt(context: FaceoffContext, mode: str) -> tuple[str, str]:
    root = files("ambassador").joinpath("prompts")
    instructions = root.joinpath("base.txt").read_text("utf-8")
    instructions += "\n" + root.joinpath(f"{mode}.txt").read_text("utf-8")
    instructions += "\nCurrent reform:\n" + context.game.scenario.decree_tr
    instructions += "\nCanonical world facts:\n" + "\n".join(context.game.scenario.facts_en)
    instructions += "\nSelected persona profiles (temporary and configurable):\n"
    instructions += json.dumps([asdict(p) for p in context.selected_personas], ensure_ascii=False)
    if mode == "objections":
        examples = dict(context.game.scenario.objections_by_persona)
        instructions += "\nRelevant concern examples for this reform (do not copy verbatim):\n"
        instructions += json.dumps(
            {p.id: examples.get(p.id, ()) for p in context.selected_personas}, ensure_ascii=False
        )
    payload = {"round_number": len(context.game.history) + 1}
    # Previous answers help vary new objections, but never influence this answer's grade.
    if mode == "objections":
        payload["history_as_untrusted_game_dialogue"] = [
            {"objections": [asdict(o) for o in r.objections], "player_answer": r.answer}
            for r in context.game.history
        ]
    if mode == "answer":
        payload["current_objections"] = [asdict(o) for o in context.game.current_objections]
        payload["current_untrusted_player_answer_tr"] = context.answer
    return instructions, json.dumps(payload, ensure_ascii=False)


class OpenAIEvaluator:
    def __init__(self, client: openai.AsyncOpenAI, model: str, max_output_tokens: int):
        self.client = client
        self.model = model
        self.max_output_tokens = max_output_tokens

    async def generate(self, context: FaceoffContext) -> ObjectionBatch:
        return await self.request(context, "objections", ObjectionBatch)

    async def evaluate(self, context: FaceoffContext) -> AnswerDecision:
        return await self.request(context, "answer", AnswerDecision)

    async def request(self, context: FaceoffContext, mode: str, schema: type[M]) -> M:
        instructions, dialogue = build_prompt(context, mode)
        try:
            raw = await self.client.responses.with_raw_response.parse(
                model=self.model,
                instructions=instructions,
                input=[{"role": "user", "content": dialogue}],
                text_format=schema,
                max_output_tokens=self.max_output_tokens,
                store=False,
            )
            envelope = raw.http_response.json()
            if envelope.get("status") == "incomplete":
                raise EvaluationError("PROVIDER_INCOMPLETE")
            response = raw.parse()
        except (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.NotFoundError,
            openai.BadRequestError,
        ):
            raise EvaluationError("PROVIDER_CONFIGURATION", False, 503) from None
        except openai.APITimeoutError:
            raise EvaluationError("PROVIDER_TIMEOUT", True, 504) from None
        except (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError):
            raise EvaluationError("PROVIDER_UNAVAILABLE", True, 503) from None
        except (ValidationError, openai.LengthFinishReasonError):
            raise EvaluationError("INVALID_FACEOFF_OUTPUT") from None
        except openai.APIStatusError as exc:
            transient = exc.status_code in (408, 409, 429) or exc.status_code >= 500
            raise EvaluationError(
                "PROVIDER_UNAVAILABLE" if transient else "PROVIDER_CONFIGURATION", transient, 503
            ) from None
        except openai.APIError:
            raise EvaluationError("PROVIDER_FAILURE", False) from None
        logger.info(
            "provider model=%s prompt=%s mode=%s usage=%s status=%s",
            self.model,
            PROMPT_VERSION,
            mode,
            response.usage.model_dump() if response.usage else None,
            response.status,
        )
        if any(
            part.type == "refusal"
            for item in response.output
            if item.type == "message"
            for part in item.content
        ):
            raise EvaluationError("PROVIDER_REFUSAL", False)
        if response.status != "completed" or response.output_parsed is None:
            raise EvaluationError("INVALID_FACEOFF_OUTPUT")
        return response.output_parsed
