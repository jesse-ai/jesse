from jesse.models import Position

class PositionsState:
    def __init__(self) -> None:
        self.storage = {}

    def count_open_positions(self) -> int:
        c = 0
        for key in self.storage:
            p = self.storage[key]
            if p.is_open:
                c += 1
        return c

    def get_position(self, exchange: str, symbol: str) -> Position:
        return self.storage.get(f'{exchange}-{symbol}', None)
    