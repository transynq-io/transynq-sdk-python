# Versioning and compatibility

- The SDK follows [semantic versioning](https://semver.org/). Its version (1.0.0) is independent of the API version.
- **Patch** releases fix bugs. **Minor** releases add operations, models or members (generated from a newer contract) and
  options. **Major** releases change or remove public signatures.
- The API is versioned in its path (`/api/v1`) and only makes additive changes within a version. Every answer carries
  `X-Api-Version`.
- The package version is in `pyproject.toml` and `transynq.__version__`; `transynq.SPEC_SHA256` and `transynq.API_VERSION` say which contract the code was generated from.
- Models ignore unknown properties and codes are open strings, so an older SDK keeps working against a newer API v1.
- Supported runtimes: Python 3.9 or later, with `httpx`, `pydantic` (v2) and `typing_extensions`. A Python version leaves the
  support matrix in a minor release after its upstream end of life.

See the [changelog](https://github.com/qadir0108/transynq-sdk-python/blob/main/CHANGELOG.md) for the changes of each release.
