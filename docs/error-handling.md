# Error handling

Every non-2xx answer becomes a typed error built from the API's ProblemDetails body
(`type`, `title`, `status`, `detail`, `code`, `correlationId`, and `errors` for validation).

| Status | `code` (examples) | Python exception |
|---|---|---|
| 400 | `validation`, `unreadable-request` | `ValidationError` (`errors`) |
| 401 | `invalid-token` or none | `AuthenticationError` |
| 403 | `forbidden` or none | `PermissionDeniedError` |
| 404 | `not-found`, `unknown-company` | `NotFoundError` |
| 409 | `conflict` | `ConflictError` |
| 412 | `stale-version` | `StaleVersionError` |
| 422 | the rule: `year-exists`, `id-in-use`, `rule-violated`, `mail-held-back`... | `BusinessRuleError` |
| 429 | none (`Retry-After` header) | `RateLimitError` (`retry_after`, seconds) |
| 5xx | `unexpected`, `not-implemented` (501) | `ServerError` |
| other 4xx | as sent | `ApiError` |
| no answer | - | `ConnectionError` / `TimeoutError` |

Every `ApiError` exposes `status`, `code`, `title`, `detail`, `type`, `correlation_id`, `raw_body`, `headers` and `operation_id`. All SDK errors derive from `TransynqError`; a failed long operation raises `LongOperationFailedError` (`operation`). `transynq.ConnectionError` and `transynq.TimeoutError` are the SDK's own classes (import them from `transynq`), not the built-ins.

```python
from transynq import ApiError, BusinessRuleError, ConnectionError, RateLimitError, ValidationError

try:
    client.reference_data.create_public_holiday(holiday)
except ValidationError as e:               # 400
    for field, messages in e.errors.items():
        print(field, "; ".join(messages))
except BusinessRuleError as e:             # 422
    print(f"Refused by rule {e.code}: {e.detail}")
except RateLimitError as e:                # 429 after retries
    print(f"Try again in {e.retry_after} s")
except ApiError as e:                      # any other answer
    print(e.status, e.code, e.title, "- quote correlation id", e.correlation_id)
except ConnectionError as e:               # no answer (transynq.TimeoutError derives from it)
    print(e)
```

## What the fields mean

- `code` is stable across languages and releases: branch on it, not on `title` (the title is translated into the user's language).
- `detail` is the business rule's sentence for 422 answers.
- `correlationId` identifies the request in the API's logs. It is in every problem body and in the `X-Correlation-Id` header;
  quote it when you contact support. The SDK sends its own correlation id on every request (the same on every retry of one call).
- Out-of-scope ids answer **404**, never 403: you cannot tell "missing" from "not yours".
- A 400 is also returned when `If-Match` is missing on a PUT or DELETE that requires it.

## Retries happen before you see an error

Retryable failures (see [Configuration](configuration.md#retries)) are retried first; the error you catch is the last answer.
