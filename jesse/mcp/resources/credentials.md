# Credential Management Reference

Jesse stores two kinds of credentials locally, both managed from the Dashboard and from MCP:

- **Exchange API keys** — used by Jesse Live to trade on an exchange.
- **Data provider credentials** — used for historical imports; today this is the single
  Massive API key shared by Massive Stocks, Massive Currencies, Massive Indices, and
  Massive Futures.

MCP can store, list, and delete them. It cannot read a stored secret back: every result is
metadata only (ids, names, exchange or provider, timestamps, field requirements), with no key,
secret, or masked fragment of one. Errors never quote submitted values. The Dashboard's
password-confirmed CSV export is the only way to get stored secrets out, and MCP has no
equivalent.

## Conduct

- Only store a secret the user provided in this conversation. Never invent, reuse, or infer one,
  and never repeat a key or secret back to the user.
- Refer to stored keys by `name` and `id`. A saved `id` is all later steps need; nothing requires
  the secret again.
- Delete only what the user asked to remove; deletion is permanent.

## Exchange API keys

### get_exchange_api_key_requirements(exchange=None)

Lists every live-trading exchange that accepts API keys (the same list as the Dashboard form)
and its fields: `{key, label, location, required, format}`. `location: "argument"` is a
`store_exchange_api_key()` parameter; `location: "additional_fields"` is a key of its
`additional_fields` object.

| Exchange (by name) | `api_key` / `api_secret` labels | `additional_fields` |
|--------------------|----------------------------------|---------------------|
| Most exchanges | API Key / API Secret | none |
| Hyperliquid … | Wallet Address / Private Key | none |
| Lighter … | L1 Wallet Address / API Private Key | `api_key_index` (integer, required), `account_index` (integer, optional; derived from the wallet when omitted) |
| Apex … | API Key / API Secret | `api_passphrase`, `wallet_address`, `stark_private_key` (all required) |
| KuCoin … | API Key / API Secret | `api_passphrase` (required) |

Always check the tool for the exact exchange names; historical-only sources such as
"Massive Stocks" are not listed and take no exchange key.

### get_exchange_api_keys()

**Returns:** `exchange_api_keys`: `[{id, name, exchange, created_at}]`.

The `id` is the value a live session stores as `exchange_api_key_id` (chosen in the Dashboard's
live session form) and the input of `delete_exchange_api_key()`.

### store_exchange_api_key(exchange, name, api_key, api_secret, additional_fields=None)

- `exchange`: a name from `get_exchange_api_key_requirements()`, exactly.
- `name`: unique among stored keys (error_type `name_taken` otherwise).
- `name`, `api_key`, and `api_secret` must be 1-255 characters.
- `additional_fields`: exactly the keys the exchange lists, as strings (`format: "integer"` fields
  also take a whole number); unknown keys, missing required keys, and non-integer indexes are
  rejected before anything is saved.

**Returns:** `exchange_api_key`: `{id, name, exchange, created_at}`. Stored keys cannot be edited;
to change one, delete it and store a new one under the same or another name.

### delete_exchange_api_key(id)

Deletes the key immediately and returns its metadata; an unknown id is `not_found`. Jesse does
not check which sessions use the key: a running live session keeps the key it already loaded,
but any session whose `exchange_api_key_id` is this id cannot start again until it is given a
newly stored key.

## Data provider credentials

### get_data_provider_credentials()

**Returns:** `data_providers`: one entry per supported provider,
`{provider_id, name, configured, created_at, updated_at, credential_fields: [{key, label, secret}]}`,
plus `configured_providers`. This is how to discover supported providers and their fields;
today `Massive` takes one field, `api_key`. Timestamps are Unix milliseconds.

### store_data_provider_credentials(api_key, provider_id="Massive")

Saves the provider key. Jesse keeps exactly one key per provider and refuses to overwrite it
(error_type `already_configured`). Follow up with `validate_data_provider_credentials()`.

### delete_data_provider_credentials(provider_id="Massive")

Removes the key (`not_found` when none is stored). Candles already imported stay in the
database; new Massive imports and `search_symbols()` on Massive sources fail with an
authentication error until a key is stored.

### validate_data_provider_credentials(provider_id="Massive")

Performs a live check against the provider. Reports `status: "success"` or an error_type:
`credentials_rejected`, `missing_entitlement`, `not_configured`, `rate_limited`,
`provider_unavailable`, or `validation_failed`.

Imports need no credential id: `import_candles()` and `search_symbols()` on Massive sources use
the stored Massive key automatically.

## Errors

Every tool returns `{status: "error", error_type, message}` on failure. Besides the types above:
`invalid_request`, `unsupported_exchange`, `unsupported_provider`, `authentication_failed` (the
MCP worker's dashboard password), `connection_error`, `jesse_error`, `unexpected_response`, and
`internal_error`. Do not retry `name_taken`, `already_configured`, or validation errors unchanged.

## Workflows

**"Save my Binance key"**: `get_exchange_api_key_requirements("Binance Perpetual Futures")`,
ask only for missing fields, `store_exchange_api_key(...)`, then report the stored `name` and `id`.

**"Replace my Massive key"**: `delete_data_provider_credentials()`,
`store_data_provider_credentials(api_key)`, `validate_data_provider_credentials()`, report the result.

**"Massive imports fail with an authentication error"**: `get_data_provider_credentials()`; if
Massive is not configured, ask the user for a key and store it; otherwise validate and report.
