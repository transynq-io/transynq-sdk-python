# Publishing to PyPI

`transynq` is published to [PyPI](https://pypi.org/project/transynq/) by
[`.github/workflows/release.yml`](.github/workflows/release.yml) with **PyPI trusted publishing**: GitHub Actions gets a
short-lived OIDC token and `pypa/gh-action-pypi-publish` exchanges it for an upload token. No API token is stored anywhere.

## One-time setup (repository owner)

1. **PyPI account.** Create an account at <https://pypi.org> and enable two-factor authentication (required to publish).
2. **Pending trusted publisher** (this also reserves the project name `transynq` before the first upload).
   *Your account > Publishing > Add a new pending publisher > GitHub*, with exactly:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `transynq` |
   | Owner | `transynq-io` |
   | Repository name | `transynq-sdk-python` |
   | Workflow name | `release.yml` |
   | Environment name | `release` |

   After the first successful upload the pending publisher becomes a normal trusted publisher of the project.
3. **GitHub environment.** Repository *Settings > Environments > New environment* `release` (the same name as above). Optionally
   add **required reviewers** (manual approval before every upload) and restrict it to tags `v*`.

No secrets or variables are needed.

## Release procedure

1. Update `version` in `pyproject.toml` and `SDK_VERSION` in `src/transynq/_core/http.py` (semantic versioning; the SDK version
   is independent of the API version).
2. Move the "Unreleased" entries of [CHANGELOG.md](CHANGELOG.md) under a new `## [X.Y.Z] - YYYY-MM-DD` heading.
3. Open a pull request, let CI pass, merge to `main`.
4. Create a GitHub release with a **new tag `vX.Y.Z`** (exactly the package version with a `v` prefix) on `main`, paste the
   changelog section as notes, and publish it.
5. The `release` workflow checks the tag against the package version (it fails on a mismatch), runs ruff, mypy and pytest,
   builds the sdist and wheel, runs `twine check --strict`, and uploads them to PyPI (after the `release` environment approval,
   if configured).

**Dry run:** *Actions > release > Run workflow* with `dry-run` checked (the default) builds and checks the distributions without
uploading; they are attached to the run as the `python-dist` artifact.

PyPI never accepts the same file name twice: a published version cannot be replaced, only yanked. Fix mistakes with a new
version.
