import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from ambassador.adapters.fake import FakeEvaluator
from ambassador.adapters.memory import MemoryRepository
from ambassador.api.schemas import (
    AnswerCommand,
    CreateGame,
    ErrorEnvelope,
    GameView,
    ScenarioView,
    TurnResult,
    game_view,
    scenario_view,
    turn_view,
)
from ambassador.application.errors import OperationError
from ambassador.application.service import GameService
from ambassador.config import Settings
from ambassador.domain.game import Rules
from ambassador.scenarios.loader import load_personas, load_scenarios

logger = logging.getLogger(__name__)


def create_app(service: GameService | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    client = None
    if service is None:
        if settings.llm_backend == "fake":
            evaluator = FakeEvaluator()
        else:
            from openai import AsyncOpenAI

            from ambassador.adapters.openai import OpenAIEvaluator

            client = AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                max_retries=0,
                timeout=settings.provider_timeout_seconds,
            )
            evaluator = OpenAIEvaluator(client, settings.openai_model, settings.max_output_tokens)
        overrides = {}
        for name, value in (
            ("starting_support", settings.starting_support),
            ("target_support", settings.target_support),
            ("rounds", settings.max_rounds),
        ):
            if value is not None:
                overrides[name] = value
        scenarios = tuple(
            replace(scenario, rules=replace(scenario.rules, **overrides))
            for scenario in load_scenarios()
        )
        service = GameService(
            MemoryRepository(),
            evaluator,
            scenarios,
            load_personas(settings.personas_file),
            min_objections=settings.objections_min,
            max_objections=settings.objections_max,
            concurrency=settings.provider_concurrency,
            attempt_timeout=settings.provider_timeout_seconds,
            turn_timeout=settings.turn_timeout_seconds,
            transcript_dir=settings.transcript_dir,
            reform_generator=evaluator,
            generation_timeout=settings.generation_timeout_seconds,
            generated_rules=replace(Rules(), **overrides),
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if client is not None:
            await client.close()

    errors = {status: {"model": ErrorEnvelope} for status in (404, 409, 422, 502, 503, 504)}
    app = FastAPI(title="King's Ambassador", version="2.0.0", lifespan=lifespan, responses=errors)
    app.state.service = service

    def error_response(code: str, message: str, status: int, retryable: bool = False):
        return JSONResponse(
            status_code=status,
            content={
                "api_version": "2",
                "error": {
                    "code": code,
                    "message_tr": message,
                    "retryable": retryable,
                },
            },
        )

    @app.exception_handler(OperationError)
    async def operation_error(request: Request, exc: OperationError):
        return error_response(exc.code, exc.message_tr, exc.status, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response("INVALID_INPUT", "İstek biçimi veya alanları geçersiz.", 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(
            "HTTP_ERROR", "İstenen işlem bulunamadı veya desteklenmiyor.", exc.status_code
        )

    @app.get("/health")
    async def health():
        return {"status": "ok", "backend": settings.llm_backend, "configured": True}

    @app.get("/v2/scenarios", response_model=list[ScenarioView])
    async def scenarios():
        return [scenario_view(s) for s in service.scenarios.values()]

    @app.post("/v2/games", response_model=GameView, status_code=201)
    async def create(body: CreateGame):
        if body.topic is not None:
            return game_view(await service.create_generated(body.topic))
        assert body.scenario_id is not None
        return game_view(await service.create(body.scenario_id))

    @app.get("/v2/games/{game_id}", response_model=GameView)
    async def read(game_id: UUID):
        return game_view(service.read(str(game_id)))

    @app.post("/v2/games/{game_id}/answers", response_model=TurnResult)
    async def answer(game_id: UUID, body: AnswerCommand):
        result = await service.command(
            str(game_id), str(body.request_id), body.expected_version, body.text
        )
        return turn_view(result)

    return app
