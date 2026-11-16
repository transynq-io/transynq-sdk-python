# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Report it privately with the **Report a vulnerability** button on this repository's **Security** tab (private
vulnerability reporting), or email **contact@transynq.io** with the subject "Security". Include:

- the SDK version and language runtime version;
- what you found and how to reproduce it (a minimal program, without real credentials or customer data);
- the impact you expect.

You will get an acknowledgement within 5 working days and a plan or fix date within 30 days. Please give us a reasonable
time to release a fix before any public disclosure; we will credit you in the release notes if you wish.

## Supported versions

| Version | Supported |
|---|---|
| 1.x | yes |
| < 1.0 | no |

## What the SDK does to protect secrets

- Credentials (API keys, passwords, session cookies, CSRF tokens, driver tokens) are never logged; the request and response
  hooks receive `Authorization`, `Cookie`, `Set-Cookie`, `X-Transynq-APIKey` and `X-CSRF-Token` as `[redacted]`.
- Request and response bodies are never logged by the SDK.
- Credential objects print as `...([redacted])`.
- The session cookie is kept in memory by the credential only; it is never written to disk.

Keep keys and passwords in a secret store (environment variables injected by your platform, Azure Key Vault, AWS Secrets
Manager...), never in source control.
