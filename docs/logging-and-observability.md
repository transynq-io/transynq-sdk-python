# Logging and observability

```python
import logging

logging.basicConfig(level=logging.DEBUG)                 # the SDK logs one line per attempt to the "transynq" logger

client = TransynqClient(
    "https://api.example.com",
    credential=ApiKeyCredential(api_key),
    logger=logging.getLogger("my-app.transynq"),          # optional: your own logger
    on_request=lambda info: print("->", info["method"], info["operation_id"], "#", info["attempt"]),
    on_response=lambda info: print("<-", info["status_code"], f"{info['elapsed'] * 1000:.0f} ms"),
)
```

- The logger receives one debug line per attempt: operation id, attempt number, status (or `timeout` / network error),
  duration and correlation id. Never request or response bodies, never credentials.
- The request hook runs before every attempt (method, URL, operation id, attempt, headers); the response hook after every
  answer (status, elapsed time, headers). Credential headers are `[redacted]` in both.
- Every request carries `User-Agent: transynq-sdk-python/1.0.0` (plus your suffix) and a client-generated `X-Correlation-Id`
  (32 hex characters, the same on every retry of one call). The API logs under that id and echoes it back.

## On every response

`ApiResponse[T]` exposes `data`, `status_code`, `headers`, `etag`, `api_version` (`X-Api-Version`), `correlation_id` (`X-Correlation-Id`), `location` and `is_accepted`.

`X-Api-Version` is the version of the contract that answered; log it next to your own version to diagnose a mismatch after an
API release.
