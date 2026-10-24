import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from ambassador.domain.game import Game, Round


@dataclass(frozen=True)
class CommandResult:
    game: Game
    request_id: str
    round: Round


@dataclass
class GameEntry:
    game: Game
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    results: dict[str, tuple[str, CommandResult]] = field(default_factory=dict)


class GameRepository(Protocol):
    def add(self, game: Game) -> None: ...
    def get(self, game_id: str) -> GameEntry | None: ...
