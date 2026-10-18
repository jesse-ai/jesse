"""
Argument types shared by the research draft tools (backtest, optimization, Monte Carlo,
significance test) for their run settings; see services/draft_config.py.
"""
from typing import Annotated, Any

from pydantic import WithJsonSchema

# A JSON object, sent either as an object or as JSON text (the service parses and validates it).
ConfigOverrides = Annotated[Any, WithJsonSchema({'anyOf': [
    {'type': 'string'}, {'type': 'object', 'additionalProperties': True}, {'type': 'null'},
]})]
