# Changelog

All notable changes to this SDK are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

## [1.0.3] - 2026-11-21

### Changed

- README, package metadata and documentation link to [transynq.io](https://transynq.io/) and the [Transynq TMS](https://transynq.io/transport-management-system) page, with a clearer description, keywords and an About Transynq section.

## [1.0.2] - 2026-11-16

### Changed

- The project moved to the **Transynq** GitHub organization: https://github.com/transynq-io/transynq-sdk-python. Package metadata, documentation and badge links point there (old links redirect).
- Security reports go through GitHub private vulnerability reporting or contact@transynq.io; conduct reports to contact@transynq.io.

## [1.0.1] - 2026-11-16

### Fixed

- README links to the licence, docs and examples are absolute, so they work on PyPI.

## [1.0.0] - 2026-11-16

### Added

- First release of the Python SDK, generated from the Transynq API OpenAPI contract v1.0.0
  (SHA-256 `b48b3082dfaf0d1b177dd7b8704dfbeae4bfae2d3e57fae39705242e37a6a558`): 705 operations in 52 resource groups, 560 models.
- Credentials: API key (`X-Transynq-APIKey`), session sign-in with cookie and CSRF handling, driver login and driver token.
- Typed errors from ProblemDetails; retries with exponential back-off, jitter and `Retry-After`; per-call options.
- ETag / If-Match helpers, idempotent creates by client id, `Idempotency-Key`.
- Auto-paging, grid row iteration, long-running operation poller, multipart uploads and streamed downloads.
- Request/response hooks with secret redaction, correlation ids and `X-Api-Version` on every response.
- Requires Python 3.10 or later.
- Transynq branding for README, docs and package metadata.

[Unreleased]: https://github.com/transynq-io/transynq-sdk-python/compare/v1.0.3...HEAD
[1.0.3]: https://github.com/transynq-io/transynq-sdk-python/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/transynq-io/transynq-sdk-python/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/transynq-io/transynq-sdk-python/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/transynq-io/transynq-sdk-python/releases/tag/v1.0.0
