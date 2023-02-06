class EmptyPosition(Exception):
    pass


class OpenPositionError(Exception):
    pass


class OrderNotAllowed(Exception):
    pass


class ConflictingRules(Exception):
    pass


class InvalidStrategy(Exception):
    pass


class CandleNotFoundInDatabase(Exception):
    pass


class CandleNotFoundInExchange(Exception):
    pass


class SymbolNotFound(Exception):
    pass


class RouteNotFound(Exception):
    pass


class InvalidRoutes(Exception):
    pass


class ExchangeInMaintenance(Exception):
    pass


class ExchangeNotResponding(Exception):
    pass


class ExchangeRejectedOrder(Exception):
    pass


class InvalidShape(Exception):
    pass


class InvalidConfig(Exception):
    pass


class InvalidTimeframe(Exception):
    pass


class InvalidSymbol(Exception):
    pass


class NegativeBalance(Exception):
    pass


class InsufficientMargin(Exception):
    pass


class InsufficientBalance(Exception):
    pass


class Termination(Exception):
    pass


class InvalidExchangeApiKeys(Exception):
    pass


class ExchangeError(Exception):
    pass


class NotSupportedError(Exception):
    pass
