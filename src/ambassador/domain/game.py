from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4

MIN_SCORE = -30
MAX_SCORE = 30


class Phase(StrEnum):
    FACEOFF = "faceoff"
    FINISHED = "finished"


@dataclass(frozen=True)
class Persona:
    id: str
    name_tr: str
    personality: str
    interests: str
    objection_examples_tr: tuple[str, ...]
    surname_tr: str = ""


@dataclass(frozen=True)
class VisualEffect:
    id: str
    description_tr: str


@dataclass(frozen=True)
class Rules:
    starting_support: int = 30
    target_support: int = 60
    rounds: int = 3

    def __post_init__(self) -> None:
        if not 0 <= self.starting_support <= 100 or not 1 <= self.target_support <= 100:
            raise ValueError("Support percentages must be within bounds")
        if self.rounds < 1:
            raise ValueError("Invalid faceoff rules")


@dataclass(frozen=True)
class Concern:
    id: str
    focus_en: str
    example_tr: str


@dataclass(frozen=True)
class Scenario:
    id: str
    title_tr: str
    decree_tr: str
    public_facts_tr: tuple[str, ...]
    facts_en: tuple[str, ...]
    objections_by_persona: tuple[tuple[str, tuple[str, ...]], ...] = ()
    visual_effect: VisualEffect | None = None
    rules: Rules = field(default_factory=Rules)
    concerns: tuple[Concern, ...] = ()


@dataclass(frozen=True)
class Objection:
    id: str
    persona_id: str
    name_tr: str
    text_tr: str
    concern_id: str = ""


@dataclass(frozen=True)
class Assessment:
    objection_id: str
    score: int

    def __post_init__(self) -> None:
        if type(self.score) is not int or not MIN_SCORE <= self.score <= MAX_SCORE:
            raise ValueError("Assessment score must be an integer from -30 to 30")


@dataclass(frozen=True)
class Round:
    number: int
    objections: tuple[Objection, ...]
    answer: str
    assessments: tuple[Assessment, ...]
    feedback_tr: str
    support_before: int
    support_after: int

    @property
    def delta(self) -> int:
        return self.support_after - self.support_before


@dataclass
class Game:
    scenario: Scenario
    rules: Rules
    personas: tuple[Persona, ...]
    id: str = field(default_factory=lambda: str(uuid4()))
    version: int = 0
    phase: Phase = Phase.FACEOFF
    support_percent: int = field(init=False)
    current_objections: tuple[Objection, ...] = ()
    history: list[Round] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.support_percent = self.rules.starting_support

    def commit_answer(
        self,
        answer: str,
        assessments: tuple[Assessment, ...],
        feedback_tr: str,
        next_objections: tuple[Objection, ...],
    ) -> Round:
        if self.phase == Phase.FINISHED:
            raise ValueError("Game finished")
        expected = [o.id for o in self.current_objections]
        if not expected or [a.objection_id for a in assessments] != expected:
            raise ValueError("Assessments must match current objections in order")
        last = len(self.history) + 1 == self.rules.rounds
        if (last and next_objections) or (not last and not 1 <= len(next_objections) <= 3):
            raise ValueError("Invalid next faceoff")
        requested_delta = round(sum(a.score for a in assessments) / len(assessments))
        after = max(0, min(100, self.support_percent + requested_delta))
        result = Round(
            len(self.history) + 1,
            self.current_objections,
            answer,
            assessments,
            feedback_tr,
            self.support_percent,
            after,
        )
        self.history.append(result)
        self.support_percent = after
        self.current_objections = next_objections
        self.version += 1
        if last:
            self.phase = Phase.FINISHED
        return result
