# Testing your integration

Unit tests should not call the real API. Answer the SDK's requests in memory:

```python
import httpx
import respx

from transynq import ApiKeyCredential, TransynqClient


@respx.mock
def test_lists_countries() -> None:
    respx.get("https://api.example.com/api/v1/countries").respond(200, json=[{"id": 1, "name": "Australia"}])
    client = TransynqClient("https://api.example.com", credential=ApiKeyCredential("test-key"))

    countries = client.reference_data.list_countries()

    assert countries.data[0].name == "Australia"
```

The SDK sends everything through `httpx`, so `respx` (or `httpx.MockTransport` passed as `http_client=httpx.Client(transport=...)`) answers requests without a network. You can also wrap the calls your code makes behind a small class of yours and mock that.

Tips:

- Never put real API keys, passwords, hostnames or customer data in tests; use fake values such as `test-key` and
  `https://api.example.com`.
- Answer error cases with ProblemDetails bodies (`{"title": "...", "status": 422, "code": "id-in-use"}`) to exercise your error
  handling; the SDK maps them to the same typed errors as in production.
- Set the client's max retries to 0 in tests that answer 5xx, or retries will consume your queued answers.
