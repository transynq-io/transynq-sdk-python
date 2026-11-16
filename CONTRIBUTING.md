# Contributing

Thank you for helping improve the Transynq Python SDK. By taking part you agree to the [code of conduct](CODE_OF_CONDUCT.md).

## How the code is organised

- The **generated** layer (models, request/query types and one service per API area) is produced by the Transynq SDK code
  generator from the API's OpenAPI contract. Generated files start with a "Generated ... Do not edit" header. **Do not edit them
  by hand**: a fix to generated code is a fix to the generator, made in the Transynq SDK workspace and regenerated into this
  repository. Pull requests that edit generated files will be asked to move the change.
- The **hand-written core** (transport, retries, credentials, errors, paging, long operations, files) is everything else in the
  source tree, together with the tests, docs and examples.

## Build, lint and test

```shell
python -m venv .venv && .venv/bin/pip install -e ".[dev,docs]"
ruff check .
mypy
pytest
python -m build
```

`ruff check .` and `mypy` (strict, with the Pydantic plugin) must be clean. Tests never call the network: requests are answered in memory.

## Pull requests

1. Open an issue first for anything larger than a small fix.
2. Keep the change focused; add or update tests, docs and examples.
3. Add a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md).
4. Make sure CI is green.
5. Never commit secrets, real hostnames or customer data.

## Releases

Releases are published by GitHub Actions from a GitHub release tagged `vX.Y.Z`; see [PUBLISHING.md](PUBLISHING.md) for the
one-time registry setup and the release procedure.

## Reporting security problems

See [SECURITY.md](SECURITY.md).
