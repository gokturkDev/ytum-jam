import json
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ambassador.domain.game import Persona, Rules, Scenario, VisualEffect


class PersonaData(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    name_tr: str = Field(min_length=1, max_length=80)
    personality: str = Field(min_length=1)
    interests: str = Field(min_length=1)
    surname_tr: str = ""
    objection_examples_tr: list[str] = Field(min_length=1)


def load_personas(path: str = "") -> tuple[Persona, ...]:
    source = Path(path) if path else files("ambassador.scenarios").joinpath("personas.json")
    data = json.loads(source.read_text("utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Configure at least one persona")
    profiles = [PersonaData.model_validate(item) for item in data]
    if len({p.id for p in profiles}) != len(profiles):
        raise ValueError("Persona IDs must be unique")
    return tuple(
        Persona(**{**p.model_dump(), "objection_examples_tr": tuple(p.objection_examples_tr)})
        for p in profiles
    )


def load_scenarios() -> tuple[Scenario, ...]:
    data = json.loads(files("ambassador.scenarios").joinpath("reforms.json").read_text("utf-8"))
    scenarios = tuple(
        Scenario(
            id=item["id"],
            rules=Rules(**item["rules"]),
            title_tr=item["title_tr"],
            decree_tr=item["decree_tr"],
            public_facts_tr=tuple(item["public_facts_tr"]),
            facts_en=tuple(item["facts_en"]),
            objections_by_persona=tuple(
                (pid, tuple(examples)) for pid, examples in item["objections_by_persona"].items()
            ),
            visual_effect=VisualEffect(**item["visual_effect"]) if item["visual_effect"] else None,
        )
        for item in data
    )
    if not scenarios or len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError("Reform IDs must be unique and nonempty")
    return scenarios


def default_scenario() -> Scenario:
    return load_scenarios()[0]
