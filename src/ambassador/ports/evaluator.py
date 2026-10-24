from dataclasses import dataclass
from typing import Annotated, Protocol

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from ambassador.domain.game import Game, Persona, Quality


def one_sentence(value: str) -> str:
    text = value.strip()
    core = text.rstrip(".!?…")
    if not core or any(mark in core for mark in ".!?…\n\r") or text[-1] not in ".!?…":
        raise ValueError("Use one short sentence with terminal punctuation and no abbreviations")
    return text


Sentence = Annotated[str, Field(min_length=2, max_length=180), AfterValidator(one_sentence)]


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ObjectionProposal(Output):
    persona_id: str
    text_tr: Sentence


class ObjectionBatch(Output):
    objections: list[ObjectionProposal] = Field(min_length=1, max_length=3)


class AssessmentProposal(Output):
    objection_id: str
    quality: Quality


class AnswerDecision(Output):
    assessments: list[AssessmentProposal] = Field(min_length=1, max_length=3)
    feedback_tr: Sentence


@dataclass(frozen=True)
class FaceoffContext:
    game: Game
    selected_personas: tuple[Persona, ...]
    # Nonempty only when judging an answer, never interpreted as simulation instructions.
    answer: str | None = None


class FaceoffEvaluator(Protocol):
    async def generate(self, context: FaceoffContext) -> ObjectionBatch: ...
    async def evaluate(self, context: FaceoffContext) -> AnswerDecision: ...
