from typing import Annotated, Protocol

from pydantic import Field, StringConstraints

from ambassador.domain.game import Persona, Scenario
from ambassador.ports.evaluator import Output, Sentence

ReformTopic = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500)
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ReformDraft(Output):
    title_tr: Annotated[ShortText, Field(max_length=100)]
    decree_tr: Annotated[ShortText, Field(max_length=500)]
    public_facts_tr: list[ShortText] = Field(min_length=2, max_length=5)
    facts_en: list[ShortText] = Field(min_length=2, max_length=5)


class PersonaConcerns(Output):
    objections_tr: list[Sentence] = Field(min_length=3, max_length=3)


class ReformGenerator(Protocol):
    async def draft_reform(self, topic: str) -> ReformDraft: ...

    async def generate_concerns(self, scenario: Scenario, persona: Persona) -> PersonaConcerns: ...
