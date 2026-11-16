<p align="center">
  <img alt="Transynq - Intelligent Transport Operations" src="https://raw.githubusercontent.com/transynq-io/transynq-sdk-python/main/assets/brand/transynq-readme-banner.png" width="720">
</p>

<h1 align="center">Python SDK for the Transynq TMS API</h1>

<p align="center"><em>Intelligent Transport Operations</em></p>

<p align="center">
  <a href="https://github.com/transynq-io/transynq-sdk-python/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/transynq-io/transynq-sdk-python/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/transynq-io/transynq-sdk-python/actions/workflows/release.yml"><img alt="Release" src="https://github.com/transynq-io/transynq-sdk-python/actions/workflows/release.yml/badge.svg"></a>
  <a href="https://pypi.org/project/transynq/"><img alt="PyPI" src="https://img.shields.io/pypi/v/transynq?logo=pypi&logoColor=white&color=2563EB"></a>
  <a href="https://pypi.org/project/transynq/"><img alt="Downloads" src="https://img.shields.io/pypi/dm/transynq?color=06B6D4"></a>
  <img alt="Runtime" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?logo=python&logoColor=white">
  <a href="https://github.com/transynq-io/transynq-sdk-python/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-8B5CF6"></a>
  <a href="https://github.com/transynq-io/transynq-sdk-python/tree/main/docs/"><img alt="Docs" src="https://img.shields.io/badge/docs-guides-2563EB"></a>
  <img alt="API operations" src="https://img.shields.io/badge/API%20operations-705-0B1220">
</p>

The official Python client for **Transynq TMS** (`/api/v1`): all 705 operations of the API, grouped by area (jobs,
bookings, dispatch, invoicing, customers, driver app...), with typed models, authentication, retries, typed errors, paging,
optimistic concurrency, file transfer and long-running operations handled for you.

- Package: `transynq` - version 1.0.1 (semantic versioning, independent of the API version)
- Generated from the Transynq API OpenAPI 3.1 contract v1.0.0 plus a hand-written core
- Licence: [MIT](https://github.com/transynq-io/transynq-sdk-python/blob/main/LICENSE)

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

See [docs/authentication.md](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/authentication.md) for sessions, CSRF and driver tokens.

## Documentation

- [Getting started](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/getting-started.md)
- [Authentication](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/authentication.md)
- [Configuration](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/configuration.md)
- [Error handling](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/error-handling.md)
- [Pagination and grid queries](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/pagination.md)
- [Concurrency (ETag / If-Match)](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/concurrency.md)
- [Idempotency](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/idempotency.md)
- [Long-running operations](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/long-running-operations.md)
- [File upload and download](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/files.md)
- [Logging and observability](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/logging-and-observability.md)
- [Dates, money and enums (type mapping)](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/types.md)
- [Testing your integration](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/testing.md)
- [Versioning and compatibility](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/versioning.md)
- [Troubleshooting and FAQ](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/troubleshooting.md)
- [Resource index (every operation, generated)](https://github.com/transynq-io/transynq-sdk-python/blob/main/docs/resources/README.md)

Runnable samples of real flows (sign in, list and page grid rows, create a booking idempotently, update with If-Match, list
invoices, upload a POD, wait on a long operation) are in [`examples/flows.py`](https://github.com/transynq-io/transynq-sdk-python/blob/main/examples/flows.py).

The API reference is built from the docstrings with MkDocs Material + mkdocstrings (`mkdocs.yml` in this repository):

```shell
pip install -e ".[docs]"
mkdocs build --strict   # writes site/ (not checked in)
```

## Support

- Bugs and feature requests: [GitHub issues](https://github.com/transynq-io/transynq-sdk-python/issues) (use the templates; never paste real keys, passwords or customer data).
- Security problems: see [SECURITY.md](https://github.com/transynq-io/transynq-sdk-python/blob/main/SECURITY.md) - do not open a public issue.
- When the API answers with an error, quote its correlation id (`correlationId` on the error).

## Contributing

See [CONTRIBUTING.md](https://github.com/transynq-io/transynq-sdk-python/blob/main/CONTRIBUTING.md) and the [code of conduct](https://github.com/transynq-io/transynq-sdk-python/blob/main/CODE_OF_CONDUCT.md).

## Licence

[MIT](https://github.com/transynq-io/transynq-sdk-python/blob/main/LICENSE) - Copyright (c) 2026 Transynq.

The Transynq name and logos are trademarks of Transynq and are not covered by the MIT licence; you may use them only to refer to Transynq.
