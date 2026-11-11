# Credential Management Reference

Jesse stores two kinds of credentials locally, both managed from the Dashboard and from MCP:

- **Exchange API keys** — used by Jesse Live to trade on an exchange.
- **Data provider credentials** — used for historical imports; one API key per provider. The
  Massive key is shared by Massive Stocks, Massive Currencies, Massive Indices, and Massive
  Futures; the FMP (Financial Modeling Prep) key by FMP Stocks, FMP Currencies, FMP Indices,
  and FMP Commodities.

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
"Massive Stocks" or "FMP Stocks" are not listed and take no exchange key.

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
today there are two, `Massive` and `FMP` (name "Financial Modeling Prep"), and each takes one
field, `api_key`. Timestamps are Unix milliseconds.

### store_data_provider_credentials(api_key, provider_id="Massive")

Saves the provider key. Pass `provider_id="FMP"` for an FMP key; the default is Massive. Jesse
keeps exactly one key per provider and refuses to overwrite it (error_type
`already_configured`). Follow up with `validate_data_provider_credentials()` for the same
`provider_id`.

### delete_data_provider_credentials(provider_id="Massive")

Removes that provider's key (`not_found` when none is stored); the other provider's key is
untouched. Candles already imported stay in the database; new imports and `search_symbols()` on
that provider's sources fail with an authentication error until a key is stored.

### validate_data_provider_credentials(provider_id="Massive")

Performs a live check against the provider. Reports `status: "success"` or an error_type:
`credentials_rejected`, `missing_entitlement`, `not_configured`, `rate_limited`,
`provider_unavailable`, or `validation_failed`. For FMP the check also confirms the plan
includes one-minute intraday data; a plan without it reports `missing_entitlement`, and such a
key cannot be used for imports.

Imports need no credential id: `import_candles()` and `search_symbols()` on Massive or FMP
sources use that provider's stored key automatically.

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
For an FMP key, pass `provider_id="FMP"` to each of the three calls.

**"Massive or FMP imports fail with an authentication or entitlement error"**:
`get_data_provider_credentials()`; if that provider is not configured, ask the user for a key and
store it with its `provider_id`; otherwise validate it and report the result.

**"I don't have an FMP account"** or "where do I get an FMP key?": send the user to
https://jesse.trade/fmp, Jesse's referral link to FMP; signing up through it gives 15% off. Use
this link whenever you point a user to FMP's website.
