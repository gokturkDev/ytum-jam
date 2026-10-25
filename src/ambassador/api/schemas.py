from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ambassador.domain.game import Game, Objection, Phase, Round, Scenario, VisualEffect
from ambassador.ports.reform_generator import ReformTopic
from ambassador.ports.repository import CommandResult


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateGame(DTO):
    scenario_id: str | None = Field(default=None, min_length=1, max_length=80, strict=True)
    topic: ReformTopic | None = None

    @model_validator(mode="after")
    def one_source(self) -> "CreateGame":
        if (self.scenario_id is None) == (self.topic is None):
            raise ValueError("Provide exactly one of scenario_id or topic")
        return self


class AnswerCommand(DTO):
    request_id: UUID
    expected_version: int = Field(ge=0, strict=True)
    text: str = Field(strict=True)

    @field_validator("text")
    @classmethod
    def valid_text(cls, value: str) -> str:
        if not 1 <= len(value.strip()) <= 6000:
            raise ValueError("Answer must contain 1-6000 trimmed Unicode characters")
        return value


class NameUpdate(DTO):
    persona_id: str
    name_tr: str


class VisualEffectView(DTO):
    id: str
    description_tr: str
    name_updates: list[NameUpdate] = Field(default_factory=list)


class ScenarioView(DTO):
    id: str
    title_tr: str
    decree_tr: str
    public_facts_tr: list[str]
    visual_effect: VisualEffectView | None
    starting_support: int
    target_support: int
    rounds: int


class ObjectionView(DTO):
    objection_id: str
    persona_id: str
    name_tr: str
    text_tr: str = Field(min_length=2, max_length=180)


class AssessmentView(DTO):
    objection_id: str
    score: int = Field(ge=-20, le=20)


class RoundView(DTO):
    round_number: int
    objections: list[ObjectionView] = Field(min_length=1, max_length=3)
    answer: str
    assessments: list[AssessmentView] = Field(min_length=1, max_length=3)
    feedback_tr: str
    support_before: int
    support_after: int
    support_delta: int


class ScoringView(DTO):
    minimum: Literal[-20] = -20
    maximum: Literal[20] = 20


class Outcome(DTO):
    won: bool
    support_percent: int
    required_percent: int
    message_tr: str
    visual_effects: list[VisualEffectView]


class GameView(DTO):
    api_version: Literal["2"] = "2"
    game_id: UUID
    version: int
    scenario: ScenarioView
    phase: Phase
    rounds_completed: int
    total_rounds: int
    round_number: int | None
    support_percent: int = Field(ge=0, le=100)
    target_percent: int = Field(ge=1, le=100)
    scoring: ScoringView
    current_objections: list[ObjectionView] = Field(max_length=3)
    history: list[RoundView]
    allowed_actions: list[Literal["submit_answer"]]
    outcome: Outcome | None


class TurnResult(DTO):
    api_version: Literal["2"] = "2"
    request_id: UUID
    round: RoundView
    game: GameView


class ErrorDetail(DTO):
    code: str
    message_tr: str
    retryable: bool


class ErrorEnvelope(DTO):
    api_version: Literal["2"] = "2"
    error: ErrorDetail


def objection_view(o: Objection) -> ObjectionView:
    return ObjectionView(
        objection_id=o.id, persona_id=o.persona_id, name_tr=o.name_tr, text_tr=o.text_tr
    )


def round_view(r: Round) -> RoundView:
    return RoundView(
        round_number=r.number,
        objections=[objection_view(o) for o in r.objections],
        answer=r.answer,
        assessments=[
            AssessmentView(objection_id=a.objection_id, score=a.score) for a in r.assessments
        ],
        feedback_tr=r.feedback_tr,
        support_before=r.support_before,
        support_after=r.support_after,
        support_delta=r.delta,
    )


def effect_view(effect: VisualEffect, game: Game | None = None) -> VisualEffectView:
    names = []
    if game is not None and effect.id == "show_surnames":
        names = [
            NameUpdate(persona_id=p.id, name_tr=f"{p.name_tr} {p.surname_tr}".strip())
            for p in game.personas
        ]
    return VisualEffectView(id=effect.id, description_tr=effect.description_tr, name_updates=names)


def scenario_view(scenario: Scenario) -> ScenarioView:
    return ScenarioView(
        starting_support=scenario.rules.starting_support,
        target_support=scenario.rules.target_support,
        rounds=scenario.rules.rounds,
        id=scenario.id,
        title_tr=scenario.title_tr,
        decree_tr=scenario.decree_tr,
        public_facts_tr=list(scenario.public_facts_tr),
        visual_effect=effect_view(scenario.visual_effect) if scenario.visual_effect else None,
    )


def game_view(game: Game) -> GameView:
    finished = game.phase == Phase.FINISHED
    outcome = None
    if finished:
        won = game.support_percent >= game.rules.target_support
        outcome = Outcome(
            won=won,
            support_percent=game.support_percent,
            required_percent=game.rules.target_support,
            message_tr="Zafer! Halk reformu benimsedi."
            if won
            else "Reform henüz yeterli destek bulamadı.",
            visual_effects=[effect_view(game.scenario.visual_effect, game)]
            if won and game.scenario.visual_effect
            else [],
        )
    return GameView(
        game_id=game.id,
        version=game.version,
        scenario=scenario_view(game.scenario),
        phase=game.phase,
        rounds_completed=len(game.history),
        total_rounds=game.rules.rounds,
        round_number=None if finished else len(game.history) + 1,
        support_percent=game.support_percent,
        target_percent=game.rules.target_support,
        scoring=ScoringView(),
        current_objections=[objection_view(o) for o in game.current_objections],
        history=[round_view(r) for r in game.history],
        allowed_actions=[] if finished else ["submit_answer"],
        outcome=outcome,
    )


def turn_view(result: CommandResult) -> TurnResult:
    return TurnResult(
        request_id=result.request_id, round=round_view(result.round), game=game_view(result.game)
    )
