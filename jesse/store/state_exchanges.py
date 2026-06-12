from jesse.models import Exchange
from jesse.routes import router


class ExchangesState:
    def __init__(self) -> None:
        self.storage = {}

    def get_exchange(self, name: str) -> Exchange:
        if name is None:
            raise ValueError(f"name cannot be None. name: {name}")

        return self.storage.get(name, None)

    @property
    def trading_exchange(self) -> Exchange:
        return self.storage.get(router.routes[0].exchange, None)
