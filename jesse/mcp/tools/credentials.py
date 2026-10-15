"""
Jesse Credential Management Tools

MCP tools for the credentials the Dashboard manages under "Exchange API Keys" and
"Data Providers":

- get_exchange_api_key_requirements: Live-trading exchanges and the credential fields each accepts
- get_exchange_api_keys: List stored exchange API keys (metadata only)
- store_exchange_api_key: Add an exchange API key for Jesse Live
- delete_exchange_api_key: Remove an exchange API key
- get_data_provider_credentials: Supported data providers, their fields, and which are configured
- store_data_provider_credentials: Save a data provider API key
- delete_data_provider_credentials: Remove a data provider API key
- validate_data_provider_credentials: Test the stored data provider key against the provider

Secrets are write-only: results carry ids, names, exchange or provider, timestamps, and field
requirements, never a stored or submitted secret or a masked fragment of one.
All tools require authentication via Jesse admin password.

The tools are async and run their API calls in a worker thread (see offload.py), except
get_exchange_api_key_requirements, which only reads Jesse's exchange list and stays
synchronous. Stores and deletes of this worker never overlap (see services/locks.py).
"""

from typing import Annotated, Any

from pydantic import WithJsonSchema

from jesse.mcp.tools.offload import run_blocking
from jesse.mcp.tools.services.locks import CREDENTIALS_LOCK, serialized
from jesse.mcp.tools.services.credentials import (
    DEFAULT_DATA_PROVIDER,
    delete_data_provider_credentials_service,
    delete_exchange_api_key_service,
    get_data_provider_credentials_service,
    get_exchange_api_key_requirements_service,
    get_exchange_api_keys_service,
    store_data_provider_credentials_service,
    store_exchange_api_key_service,
    validate_data_provider_credentials_service,
)


# FastMCP validates arguments with pydantic before a tool runs, and its validation errors quote
# the offending input; a missing required argument quotes every argument, secrets included.
# Credential parameters therefore accept any value and default to None, so the services do all
# validation with messages that never repeat a value. WithJsonSchema keeps the advertised types;
# the docstrings say which arguments are required.
_Text = Annotated[Any, WithJsonSchema({'type': 'string'})]
_AdditionalFields = Annotated[Any, WithJsonSchema({
    'type': 'object',
    'additionalProperties': {'anyOf': [{'type': 'string'}, {'type': 'integer'}]},
})]

# Credential changes check and then write, so they run one at a time (see services/locks.py).
_store_exchange_api_key = serialized(CREDENTIALS_LOCK, store_exchange_api_key_service)
_delete_exchange_api_key = serialized(CREDENTIALS_LOCK, delete_exchange_api_key_service)
_store_data_provider_credentials = serialized(CREDENTIALS_LOCK, store_data_provider_credentials_service)
_delete_data_provider_credentials = serialized(CREDENTIALS_LOCK, delete_data_provider_credentials_service)


def register_credentials_tools(mcp):
    """Register the credential management tools with the MCP server."""

    @mcp.tool()
    def get_exchange_api_key_requirements(exchange: _Text = None) -> dict:
        """List the live-trading exchanges that accept API keys and the fields each one needs.

        Returns `exchanges`: [{exchange, fields: [{key, label, location, required, format}]}].
        `location` "argument" means a store_exchange_api_key() parameter (api_key, api_secret);
        "additional_fields" means a key of its `additional_fields` object. Pass `exchange` to get
        one exchange only. Call this before storing a key for an exchange you have not used yet.
        """
        return get_exchange_api_key_requirements_service(exchange)

    @mcp.tool()
    async def get_exchange_api_keys() -> dict:
        """List the exchange API keys stored for Jesse Live as metadata only.

        Returns `exchange_api_keys`: [{id, name, exchange, created_at}]. The `id` is what
        delete_exchange_api_key() takes and what a live session stores as its
        exchange_api_key_id. Stored secrets cannot be retrieved by any tool.
        """
        return await run_blocking(get_exchange_api_keys_service)

    @mcp.tool()
    async def store_exchange_api_key(
        exchange: _Text = None,
        name: _Text = None,
        api_key: _Text = None,
        api_secret: _Text = None,
        additional_fields: _AdditionalFields = None,
    ) -> dict:
        """Store an exchange API key so Jesse Live can trade on that exchange.

        `exchange`, `name`, `api_key`, and `api_secret` are required.

        - `exchange`: a name from get_exchange_api_key_requirements(), e.g.
          "Binance Perpetual Futures". Data sources such as "Massive Stocks" take no exchange
          keys; use store_data_provider_credentials() for those.
        - `name`: a unique label the user will recognize, e.g. "Main Binance account".
        - `api_key` / `api_secret`: the exchange's labels differ (Hyperliquid: wallet address and
          private key; Lighter: L1 wallet address and API private key).
        - `additional_fields`: only the keys get_exchange_api_key_requirements() lists for the
          exchange (Apex, KuCoin, Lighter); anything else is rejected. Values are strings;
          fields whose format is "integer" also accept a whole number.

        Only pass secrets the user provided in this conversation, and never repeat them back.
        Returns `exchange_api_key`: {id, name, exchange, created_at}. Stored keys cannot be edited;
        to change one, delete it and store a new one.
        """
        return await run_blocking(
            _store_exchange_api_key,
            exchange=exchange,
            name=name,
            api_key=api_key,
            api_secret=api_secret,
            additional_fields=additional_fields,
        )

    @mcp.tool()
    async def delete_exchange_api_key(id: _Text = None) -> dict:
        """Delete one stored exchange API key by the `id` (required) from get_exchange_api_keys().

        Deletion is immediate and permanent. Jesse does not check which live sessions use the
        key: a running session keeps the key it loaded, but no session using this id can start
        again until it is given a newly stored key. Returns the deleted key's metadata.
        """
        return await run_blocking(_delete_exchange_api_key, id)

    @mcp.tool()
    async def get_data_provider_credentials() -> dict:
        """List the supported historical data providers and which have an API key stored.

        Returns `data_providers`: [{provider_id, name, configured, created_at, updated_at,
        credential_fields: [{key, label, secret}]}] and `configured_providers`. Today the only
        provider is "Massive", whose single key unlocks Massive Stocks, Currencies, Indices,
        and Futures imports. The key itself is never returned.
        """
        return await run_blocking(get_data_provider_credentials_service)

    @mcp.tool()
    async def store_data_provider_credentials(api_key: _Text = None, provider_id: _Text = DEFAULT_DATA_PROVIDER) -> dict:
        """Save a data provider API key (`api_key`, required; default provider: "Massive") for historical imports.

        Jesse keeps one key per provider and refuses to overwrite it (error_type
        "already_configured"): to replace it, call delete_data_provider_credentials() first.
        Only pass a key the user provided in this conversation, and never repeat it back. Then
        call validate_data_provider_credentials() to confirm the provider accepts it.
        """
        return await run_blocking(_store_data_provider_credentials, api_key=api_key, provider_id=provider_id)

    @mcp.tool()
    async def delete_data_provider_credentials(provider_id: _Text = DEFAULT_DATA_PROVIDER) -> dict:
        """Remove a data provider's stored API key (default provider: "Massive").

        Candles already imported from that provider stay in the database; new imports and
        symbol searches for its sources fail until a key is stored again.
        """
        return await run_blocking(_delete_data_provider_credentials, provider_id=provider_id)

    @mcp.tool()
    async def validate_data_provider_credentials(provider_id: _Text = DEFAULT_DATA_PROVIDER) -> dict:
        """Test the stored data provider key against the provider (default provider: "Massive").

        Use this after store_data_provider_credentials() or when Massive imports fail with an
        authentication or entitlement error. Reports success or an error_type
        (credentials_rejected, missing_entitlement, not_configured, rate_limited,
        provider_unavailable, validation_failed) without returning the key.
        """
        return await run_blocking(validate_data_provider_credentials_service, provider_id=provider_id)
