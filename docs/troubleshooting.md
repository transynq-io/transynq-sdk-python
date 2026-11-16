# Troubleshooting and FAQ

- **401 on every call with an API key** - the key is unknown or inactive, or it is sent to the wrong host. Keys are sent as
  `X-Transynq-APIKey`; the Authentication group's `GetApiClient` operation tells which company a working key acts for.
- **403 "Missing or invalid X-CSRF-Token."** - a cookie-session request without the token. Use `SessionCredential` (it adds the
  token); do not copy cookies into custom headers yourself.
- **401 after some idle time with a session** - the session timed out; the credential signs in again once automatically. If it
  keeps failing, the account may be locked or deactivated.
- **429 Too Many Requests** - the API rate limits per address (sign-in: 10 per minute). The SDK honours `Retry-After`; reuse one
  client instead of signing in per request.
- **400 with `errors`** - read the per-field messages on the validation error; a missing `If-Match` on PUT/DELETE is also a 400.
- **412 stale-version** - someone saved the record first; use the read-modify-write helper ([Concurrency](concurrency.md)).
- **422 `id-in-use`** - a create reused a client id with different data; generate a new id for a new record.
- **404 for a record you can see in the UI** - out-of-scope records answer 404 (for example a customer user outside its
  customers, or an API key of another company).
- **A method returns a `ResponseBody` instead of a model** - the contract does not declare that operation's answer; read it as
  JSON (see [Files](files.md#operations-with-an-undeclared-answer)).
- **Where is the list of jobs?** - large lists are grid queries (`POST /api/v1/grids/{id}/query`); see [Pagination](pagination.md).
- **`pydantic.ValidationError` on an answer** - a required member was missing from the answer. The SDK validates answers against the contract; report it with the correlation id.

Still stuck? Open an issue with the SDK version, the operation id and the correlation id (never credentials).
