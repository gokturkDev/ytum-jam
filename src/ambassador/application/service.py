import asyncio
import copy
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter

from ambassador.application.errors import EvaluationError, OperationError
from ambassador.domain.game import Assessment, Game, Objection, Persona, Phase, Rules, Scenario
from ambassador.ports.evaluator import (
    AnswerDecision,
    FaceoffContext,
    FaceoffEvaluator,
    ObjectionBatch,
)
from ambassador.ports.reform_generator import (
    PersonaConcerns,
    ReformDraft,
    ReformGenerator,
    ReformTopic,
)
from ambassador.ports.repository import CommandResult, GameEntry, GameRepository

logger = logging.getLogger(__name__)
T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)


class GameService:
    def __init__(
        self,
        repository: GameRepository,
        evaluator: FaceoffEvaluator,
        scenario: Scenario | tuple[Scenario, ...],
        personas: tuple[Persona, ...],
        rules: Rules | None = None,
        min_objections: int = 1,
        max_objections: int = 1,
        concurrency: int = 3,
        attempt_timeout: float = 30,
        turn_timeout: float = 75,
        transcript_dir: str = "",
        rng: random.Random | None = None,
        reform_generator: ReformGenerator | None = None,
        generation_timeout: float = 75,
        generated_rules: Rules | None = None,
    ):
        if not 1 <= min_objections <= max_objections <= 3 or len(personas) < min_objections:
            raise ValueError("Configure 1-3 objections and enough personas")
        self.repository = repository
        self.evaluator = evaluator
        catalog = (scenario,) if isinstance(scenario, Scenario) else scenario
        self.scenarios = {s.id: s for s in catalog}
        if not catalog or len(self.scenarios) != len(catalog):
            raise ValueError("Configure unique reform scenarios")
        self.personas = personas
        self.rules = rules
        self.min_objections = min_objections
        self.max_objections = max_objections
        self.semaphore = asyncio.Semaphore(concurrency)
        self.attempt_timeout = attempt_timeout
        self.turn_timeout = turn_timeout
        self.transcript_dir = transcript_dir
        self.rng = rng or random.Random()
        self.reform_generator = reform_generator
        self.generation_timeout = generation_timeout
        self.generated_rules = generated_rules or rules or Rules()

    async def within_deadline(self, work: Awaitable[T]) -> T:
        try:
            async with asyncio.timeout(self.turn_timeout):
                return await work
        except TimeoutError:
            raise OperationError(
                "TURN_TIMEOUT", "Yanıt zaman aşımına uğradı; tekrar deneyin.", 504, True
            ) from None
        except EvaluationError as exc:
            logger.warning("operation_failure code=%s", exc.code)
            raise OperationError(
                exc.code,
                "Yüzleşme hazırlanamadı; oyun durumu korunuyor.",
                exc.status,
                exc.retryable,
            ) from None

    async def create(self, scenario_id: str) -> Game:
        if scenario_id not in self.scenarios:
            raise OperationError("INVALID_SCENARIO", "Böyle bir senaryo yok.", 422)
        scenario = self.scenarios[scenario_id]
        game = Game(scenario, self.rules or scenario.rules, self.personas)
        game.current_objections = await self.within_deadline(self.generate(game))
        self.repository.add(game)
        return copy.deepcopy(game)

    async def create_generated(self, topic: str) -> Game:
        try:
            topic = TypeAdapter(ReformTopic).validate_python(topic)
        except ValueError:
            raise OperationError("INVALID_INPUT", "Konu 1-500 karakter olmalı.", 422) from None
        if self.reform_generator is None:
            raise OperationError("GENERATION_UNAVAILABLE", "Reform üretimi yapılandırılmamış.", 503)
        try:
            async with asyncio.timeout(self.generation_timeout):
                game = await self.prepare_generated(topic, self.reform_generator)
        except TimeoutError:
            raise OperationError(
                "GENERATION_TIMEOUT", "Reform üretimi zaman aşımına uğradı.", 504, True
            ) from None
        except EvaluationError as exc:
            logger.warning("generation_failure code=%s", exc.code)
            raise OperationError(
                exc.code, "Reform hazırlanamadı; tekrar deneyin.", exc.status, exc.retryable
            ) from None
        # Publish only after every persona and the first faceoff are ready.
        self.repository.add(game)
        return copy.deepcopy(game)

    async def prepare_generated(self, topic: str, generator: ReformGenerator) -> Game:
        draft = await self.provider_call(
            lambda: generator.draft_reform(topic), ReformDraft, "draft_reform"
        )
        scenario = Scenario(
            id=f"generated_{uuid4()}",
            title_tr=draft.title_tr,
            decree_tr=draft.decree_tr,
            public_facts_tr=tuple(draft.public_facts_tr),
            facts_en=tuple(draft.facts_en),
            rules=self.generated_rules,
        )

        async def concerns(persona: Persona) -> PersonaConcerns:
            return await self.provider_call(
                lambda: generator.generate_concerns(scenario, persona),
                PersonaConcerns,
                "generate_concerns",
            )

        # TaskGroup cancels and drains siblings on any failure or request cancellation.
        # Unwrap its exception so the usual provider error envelope is preserved.
        try:
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(concerns(persona)) for persona in self.personas]
        except* EvaluationError as failures:
            raise failures.exceptions[0] from None
        scenario = replace(
            scenario,
            objections_by_persona=tuple(
                (persona.id, tuple(task.result().objections_tr))
                for persona, task in zip(self.personas, tasks, strict=True)
            ),
        )
        game = Game(scenario, scenario.rules, self.personas)
        count = self.rng.randint(self.min_objections, min(self.max_objections, len(game.personas)))
        examples = dict(scenario.objections_by_persona)
        game.current_objections = tuple(
            Objection(f"r1-o{i}", p.id, p.name_tr, examples[p.id][0])
            for i, p in enumerate(self.rng.sample(game.personas, count), 1)
        )
        return game

    def entry(self, game_id: str) -> GameEntry:
        entry = self.repository.get(game_id)
        if entry is None:
            raise OperationError("GAME_NOT_FOUND", "Oyun bulunamadı.", 404)
        return entry

    def read(self, game_id: str) -> Game:
        return copy.deepcopy(self.entry(game_id).game)

    async def call(
        self,
        operation: Callable[[FaceoffContext], Awaitable[M]],
        context: FaceoffContext,
        schema: type[M],
        validate: Callable[[M], None],
    ) -> M:
        return await self.provider_call(
            lambda: operation(copy.deepcopy(context)), schema, operation.__name__, validate
        )

    async def provider_call(
        self,
        operation: Callable[[], Awaitable[M]],
        schema: type[M],
        name: str,
        validate: Callable[[M], None] | None = None,
    ) -> M:
        for attempt in range(2):
            started = time.monotonic()
            try:
                async with self.semaphore:
                    async with asyncio.timeout(self.attempt_timeout):
                        raw = await operation()
                output = schema.model_validate(raw.model_dump())
                if validate is not None:
                    validate(output)
                return output
            except (ValueError, AttributeError, TypeError):
                failure = EvaluationError("INVALID_FACEOFF_OUTPUT")
            except TimeoutError:
                failure = EvaluationError("PROVIDER_TIMEOUT", True, 504)
            except EvaluationError as exc:
                failure = exc
            except Exception as exc:
                logger.warning("unexpected_evaluator_failure type=%s", type(exc).__name__)
                failure = EvaluationError("PROVIDER_FAILURE", False)
            finally:
                logger.info(
                    "provider_call operation=%s attempt=%s latency=%.3f",
                    name,
                    attempt + 1,
                    time.monotonic() - started,
                )
            logger.warning("faceoff_failure code=%s", failure.code)
            if not failure.retryable or attempt == 1:
                raise failure
        raise AssertionError("unreachable")

    async def generate(self, game: Game) -> tuple[Objection, ...]:
        count = self.rng.randint(self.min_objections, min(self.max_objections, len(game.personas)))
        personas = tuple(self.rng.sample(game.personas, count))
        context = FaceoffContext(copy.deepcopy(game), personas)

        def validate(output: ObjectionBatch) -> None:
            if [o.persona_id for o in output.objections] != [p.id for p in personas]:
                raise ValueError("One objection per selected persona required")

        output = await self.call(self.evaluator.generate, context, ObjectionBatch, validate)
        return tuple(
            Objection(f"r{len(game.history) + 1}-o{i}", p.id, p.name_tr, proposal.text_tr)
            for i, (p, proposal) in enumerate(zip(personas, output.objections, strict=True), 1)
        )

    async def resolve(self, game: Game, text: str, request_id: str) -> CommandResult:
        selected_ids = {o.persona_id for o in game.current_objections}
        context = FaceoffContext(
            game, tuple(p for p in game.personas if p.id in selected_ids), text
        )

        def validate(output: AnswerDecision) -> None:
            if [a.objection_id for a in output.assessments] != [
                o.id for o in game.current_objections
            ]:
                raise ValueError("Assess each current objection exactly once, in order")

        decision = await self.call(self.evaluator.evaluate, context, AnswerDecision, validate)
        # Work only on an unpublished copy. Failure generating the next round rolls everything back.
        last = len(game.history) + 1 == game.rules.rounds
        result = game.commit_answer(
            text,
            tuple(Assessment(a.objection_id, a.score) for a in decision.assessments),
            decision.feedback_tr,
            () if last else game.current_objections,
        )
        if not last:
            game.current_objections = await self.generate(game)
        return CommandResult(game, request_id, result)

    async def command(
        self,
        game_id: str,
        request_id: str,
        expected_version: int,
        text: str,
    ) -> CommandResult:
        if not 1 <= len(text.strip()) <= 6000:
            raise OperationError("INVALID_INPUT", "Cevap 1-6000 karakter olmalı.", 422)
        fingerprint = json.dumps(["answer", expected_version, text], ensure_ascii=False)
        entry = self.entry(game_id)
        if request_id in entry.results:
            previous, result = entry.results[request_id]
            if fingerprint != previous:
                raise OperationError(
                    "REQUEST_ID_CONFLICT", "İstek kimliği başka bir cevapta kullanılmış."
                )
            return copy.deepcopy(result)
        if entry.lock.locked():
            raise OperationError(
                "GAME_BUSY", "Halk hâlâ düşünüyor; tekrar deneyin.", retryable=True
            )
        async with entry.lock:
            game = copy.deepcopy(entry.game)
            if game.version != expected_version:
                raise OperationError("STALE_VERSION", "Oyun güncellenmiş; son durumu yükleyin.")
            if game.phase == Phase.FINISHED:
                raise OperationError("WRONG_PHASE", "Oyun bitti; yeni cevap verilemez.")
            result = await self.within_deadline(self.resolve(game, text, request_id))
            entry.game = result.game
            entry.results[request_id] = (fingerprint, copy.deepcopy(result))
            logger.info(
                "turn game=%s round=%s support=%s delta=%+d",
                game.id,
                result.round.number,
                game.support_percent,
                result.round.delta,
            )
            self.record_transcript(result)
            return copy.deepcopy(result)

    def record_transcript(self, result: CommandResult) -> None:
        if not self.transcript_dir:
            return
        game = result.game
        data = {
            "api_version": "2",
            "game_id": game.id,
            "version": game.version,
            "history": [asdict(r) for r in game.history],
        }
        try:
            folder = Path(self.transcript_dir)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{game.id}-{game.version}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            logger.warning("transcript_write_failed game=%s", game.id)
