from ambassador.domain.game import Game
from ambassador.ports.repository import GameEntry


class MemoryRepository:
    def __init__(self) -> None:
        self.entries: dict[str, GameEntry] = {}

    def add(self, game: Game) -> None:
        self.entries[game.id] = GameEntry(game)

    def get(self, game_id: str) -> GameEntry | None:
        return self.entries.get(game_id)
