<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/qadir0108/transynq-sdk-python/main/assets/brand/transynq-logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/qadir0108/transynq-sdk-python/main/assets/brand/transynq-logo-light.png">
    <img alt="Transynq" src="https://raw.githubusercontent.com/qadir0108/transynq-sdk-python/main/assets/brand/transynq-logo-light.png" width="360">
  </picture>
</p>

<h1 align="center">Python SDK for the Transynq TMS API</h1>

<p align="center"><em>Intelligent Transport Operations</em></p>

The official Python client for **Transynq TMS** (`/api/v1`): all 705 operations of the API, grouped by area (jobs,
bookings, dispatch, invoicing, customers, driver app...), with typed models, authentication, retries, typed errors, paging,
optimistic concurrency, file transfer and long-running operations handled for you.

- Package: `transynq` - version 1.0.0 (semantic versioning, independent of the API version)
- Generated from the Transynq API OpenAPI 3.1 contract v1.0.0 plus a hand-written core
- Licence: [MIT](LICENSE)

## Requirements

- Python 3.10 or later
- `httpx`, `pydantic` (v2) and `typing_extensions` (installed automatically)

## Install

```shell
pip install transynq
```

## Quick start

```python
import os

from transynq import ApiKeyCredential, TransynqClient

with TransynqClient("https://api.example.com", credential=ApiKeyCredential(os.environ["TRANSYNQ_API_KEY"])) as client:
    countries = client.reference_data.list_countries()
    for country in countries.data:
        print(country.name)
    print(f"Answered by API {countries.api_version}, correlation id {countries.correlation_id}")
```

One attribute per OpenAPI tag (`client.jobs`, `client.reference_data`, `client.driver_app`...), one method per operation named after its `operationId` in snake case (`get_job`, `list_countries`). Path parameters are positional, then the body; query parameters and upload parts are keyword arguments (a name that is a Python keyword gets a trailing underscore: `from_`); `options=` takes `RequestOptions`. `AsyncTransynqClient` has the same surface with `async` methods.

Every call returns an `ApiResponse`: `ApiResponse[T]` exposes `data`, `status_code`, `headers`, `etag`, `api_version` (`X-Api-Version`), `correlation_id` (`X-Correlation-Id`), `location` and `is_accepted`.

## Authentication

The API accepts three non-browser credentials; pick the one that matches your integration.

| Credential | When | Wire |
|---|---|---|
| `ApiKeyCredential` | server-to-server integrations | `X-Transynq-APIKey: <key>` |
| `SessionCredential` | tools acting as a named user | `POST /api/v1/auth/login`, then the session cookie + `X-CSRF-Token` |
| `DriverLoginCredential` / `DriverTokenCredential` | driver / POD apps (`/api/v1/driver/*`) | `Authorization: Bearer <token>` |

```python
client = TransynqClient("https://api.example.com", credential=ApiKeyCredential("tq_example_key_123"))  # sent as X-Transynq-APIKey
who = client.authentication.get_api_client()   # {"companyId": ..., "description": ...}
print(who.data.json())
```

See [docs/authentication.md](docs/authentication.md) for sessions, CSRF and driver tokens.

## Documentation

- [Getting started](docs/getting-started.md)
- [Authentication](docs/authentication.md)
- [Configuration](docs/configuration.md)
- [Error handling](docs/error-handling.md)
- [Pagination and grid queries](docs/pagination.md)
- [Concurrency (ETag / If-Match)](docs/concurrency.md)
- [Idempotency](docs/idempotency.md)
- [Long-running operations](docs/long-running-operations.md)
- [File upload and download](docs/files.md)
- [Logging and observability](docs/logging-and-observability.md)
- [Dates, money and enums (type mapping)](docs/types.md)
- [Testing your integration](docs/testing.md)
- [Versioning and compatibility](docs/versioning.md)
- [Troubleshooting and FAQ](docs/troubleshooting.md)
- [Resource index (every operation, generated)](docs/resources/README.md)

Runnable samples of real flows (sign in, list and page grid rows, create a booking idempotently, update with If-Match, list
invoices, upload a POD, wait on a long operation) are in [`examples/flows.py`](examples/flows.py).

The API reference is built from the docstrings with MkDocs Material + mkdocstrings (`mkdocs.yml` in this repository):

```shell
pip install -e ".[docs]"
mkdocs build --strict   # writes site/ (not checked in)
```

## Support

- Bugs and feature requests: [GitHub issues](https://github.com/qadir0108/transynq-sdk-python/issues) (use the templates; never paste real keys, passwords or customer data).
- Security problems: see [SECURITY.md](SECURITY.md) - do not open a public issue.
- When the API answers with an error, quote its correlation id (`correlationId` on the error).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md).

## Licence

[MIT](LICENSE) - Copyright (c) 2026 Transynq.

The Transynq name and logos are trademarks of Transynq and are not covered by the MIT licence; you may use them only to refer to Transynq.
