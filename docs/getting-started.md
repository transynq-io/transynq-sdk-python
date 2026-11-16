# Getting started

## 1. Install

```shell
pip install transynq
```

## 2. Get a credential

Ask your Transynq administrator for an **API client key** (recommended for integrations: it is tied to one company and needs no
password), or use a user name and password for a session. Keep secrets out of source control: read them from the environment or a
secret store.

## 3. Make a first call

```python
import os

from transynq import ApiKeyCredential, TransynqClient

with TransynqClient("https://api.example.com", credential=ApiKeyCredential(os.environ["TRANSYNQ_API_KEY"])) as client:
    countries = client.reference_data.list_countries()
    for country in countries.data:
        print(country.name)
    print(f"Answered by API {countries.api_version}, correlation id {countries.correlation_id}")
```

## 4. Learn the shape of the client

One attribute per OpenAPI tag (`client.jobs`, `client.reference_data`, `client.driver_app`...), one method per operation named after its `operationId` in snake case (`get_job`, `list_countries`). Path parameters are positional, then the body; query parameters and upload parts are keyword arguments (a name that is a Python keyword gets a trailing underscore: `from_`); `options=` takes `RequestOptions`. `AsyncTransynqClient` has the same surface with `async` methods.

- Every answer is an `ApiResponse` with the data and the headers you need: `ApiResponse[T]` exposes `data`, `status_code`, `headers`, `etag`, `api_version` (`X-Api-Version`), `correlation_id` (`X-Correlation-Id`), `location` and `is_accepted`.
- About 400 operations do not declare their answer in the contract (they return JSON, a file or nothing). They return a buffered
  `ResponseBody` (bytes, content type, file name) with JSON helpers; clear file downloads return a streamed `FileDownload`.
- The [resource index](resources/README.md) lists every operation with its method name.

## 5. Next steps

- [Authentication](authentication.md) - sessions, CSRF and driver tokens.
- [Error handling](error-handling.md) - typed errors and correlation ids.
- [Pagination](pagination.md), [Concurrency](concurrency.md), [Idempotency](idempotency.md), [Long-running operations](long-running-operations.md).
- The runnable samples in `examples/flows.py` (`python examples/flows.py sign-in`).
