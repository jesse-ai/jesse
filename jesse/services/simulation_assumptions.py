from enum import Enum, IntEnum
from typing import Mapping, Any

from jesse.exceptions import InvalidConfig


class SimulationModel(str, Enum):
    SPOT = 'spot'
    PERPETUAL_FUTURES = 'perpetual_futures'


class Annualization(IntEnum):
    TRADING_252 = 252
    CALENDAR_365 = 365


_LEGACY_TYPE_TO_MODEL = {
    'spot': SimulationModel.SPOT,
    'futures': SimulationModel.PERPETUAL_FUTURES,
}
_MODEL_TO_LEGACY_TYPE = {model: legacy for legacy, model in _LEGACY_TYPE_TO_MODEL.items()}


def simulation_model_from_legacy_type(value: str) -> SimulationModel:
    try:
        return _LEGACY_TYPE_TO_MODEL[value]
    except KeyError as exc:
        raise InvalidConfig(f'Unsupported legacy exchange type: {value!r}') from exc


def legacy_type_from_simulation_model(value: SimulationModel | str) -> str:
    model = _simulation_model(value)
    return _MODEL_TO_LEGACY_TYPE[model]


def resolve_simulation_model(
    values: Mapping[str, Any],
    default_legacy_type: str,
) -> SimulationModel:
    """Resolve new and legacy run fields while rejecting contradictory payloads."""
    supplied: list[tuple[str, SimulationModel]] = []
    if values.get('simulation_model') not in (None, ''):
        supplied.append(('simulation_model', _simulation_model(values['simulation_model'])))
    if values.get('market_type') not in (None, ''):
        supplied.append(('market_type', simulation_model_from_legacy_type(str(values['market_type']))))
    if values.get('type') not in (None, ''):
        supplied.append(('type', simulation_model_from_legacy_type(str(values['type']))))

    if not supplied:
        return simulation_model_from_legacy_type(default_legacy_type)

    model = supplied[0][1]
    if any(candidate != model for _, candidate in supplied[1:]):
        fields = ', '.join(f'{name}={candidate.value!r}' for name, candidate in supplied)
        raise InvalidConfig(f'Conflicting simulation model fields: {fields}')
    return model


def resolve_annualization(values: Mapping[str, Any], default: int = Annualization.CALENDAR_365) -> Annualization:
    value = values.get('annualization', default)
    if isinstance(value, bool):
        raise InvalidConfig('Annualization must be either 252 or 365')
    if isinstance(value, str):
        if value not in ('252', '365'):
            raise InvalidConfig('Annualization must be either 252 or 365')
        value = int(value)
    if not isinstance(value, int):
        raise InvalidConfig('Annualization must be either 252 or 365')
    try:
        return Annualization(value)
    except (TypeError, ValueError) as exc:
        raise InvalidConfig('Annualization must be either 252 or 365') from exc


def _simulation_model(value: SimulationModel | str) -> SimulationModel:
    try:
        return value if isinstance(value, SimulationModel) else SimulationModel(value)
    except ValueError as exc:
        supported = ', '.join(model.value for model in SimulationModel)
        raise InvalidConfig(f'Unsupported simulation model {value!r}. Supported values: {supported}') from exc
